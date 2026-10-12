"""linux-wallpaperengine 的进程控制与状态机。

只管「起进程 / 停进程 / 判断是否真的起来了」，
作者开关在 `settings.py`，会话环境在 `session.py`。

启动后必须确认进程活着，否则会把「秒退」也报成「已加载」——这是原实现最坑的地方。
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from lwe_gui_slint import settings
from lwe_gui_slint.config import ENGINE, ENGINE_LOG, PID_FILE
from lwe_gui_slint.model import Wallpaper
from lwe_gui_slint.session import detect_monitor, engine_env

logger = logging.getLogger("lwe_gui_slint")

STATUS_IDLE = "idle"
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_BUSY = "busy"

# 启动后等多久确认没秒退
VERIFY_SECONDS = 2.0


# ---------- 进程原语 ----------

def bin_path(name: str) -> str:
    return shutil.which(name) or name


def start_detached(
    program: str, args: list[str], log_path: Path | None = None
) -> tuple[bool, int]:
    """起一个独立会话的进程；stderr 可落到指定文件。"""
    logger.debug("[EXEC] %s %s", program, " ".join(args))
    handle = None
    stderr: object = subprocess.DEVNULL
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(log_path, "wb")
        stderr = handle
    try:
        process = subprocess.Popen(
            [program, *args],
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=engine_env(),
        )
        logger.info("[EXEC] 已启动 pid=%d", process.pid)
        return True, process.pid
    except OSError as exc:
        logger.error("[EXEC] 启动失败: %s", exc)
        return False, 0
    finally:
        if handle is not None:
            handle.close()


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_pid(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def stop_pid(pid: int, timeout: float = 1.5) -> None:
    """SIGTERM → 等 → SIGKILL。只结束指定 pid，绝不用 pkill。"""
    signal_pid(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.15)
    if pid_alive(pid):
        signal_pid(pid, signal.SIGKILL)


def tail_log(path: Path, lines: int = 3) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "引擎无输出"
    tail = [line for line in text.splitlines() if line.strip()][-lines:]
    return " / ".join(tail) if tail else "引擎无输出"


# ---------- 状态机 ----------

class WallpaperEngine:
    def __init__(self, notify: Callable[[str, str], None] | None = None) -> None:
        self._notify = notify or (lambda kind, text: None)
        self.fps = 30
        self.status = "就绪"
        self.status_kind = STATUS_IDLE
        self.selected: Wallpaper | None = None
        self.last_apply_ok = False
        self.last_monitor = ""
        self._applying = False
        self._stop_on_exit = False

    # ---- 状态 ----

    def set_notify(self, notify: Callable[[str, str], None]) -> None:
        self._notify = notify

    def set_status(self, text: str, kind: str = STATUS_IDLE) -> None:
        self.status = text
        self.status_kind = kind
        self._notify(kind, text)

    def select(self, wallpaper: Wallpaper) -> None:
        self.selected = wallpaper
        self.set_status(f"已选中: {wallpaper.title[:30]}")

    def set_fps(self, value: int) -> None:
        self.fps = max(1, min(120, int(value)))

    def is_running(self) -> bool:
        result = subprocess.run(
            [bin_path("pgrep"), "-f", "[l]inux-wallpaperengine"], capture_output=True
        )
        return result.returncode == 0

    def recheck_alive(self) -> None:
        """应用后 5 秒的生存复检。

        引擎可能是 2 秒存活检查之后才崩（例如会话环境不对），
        那种情况必须改成报错，不能继续显示「已加载」。
        """
        if self.is_running():
            return
        if self.last_apply_ok and self.selected is not None:
            logger.error("[CHECK] 壁纸进程已消失，判定为启动失败")
            self.last_apply_ok = False
            self.set_status(
                f"启动失败: {self.selected.id} — {tail_log(ENGINE_LOG)}", STATUS_ERROR
            )

    # ---- 应用 / 停止 ----

    def apply(self) -> None:
        self.last_apply_ok = False
        if self.selected is None:
            logger.warning("[APPLY] 未选择壁纸")
            self.set_status("请先选择一个壁纸", STATUS_ERROR)
            return
        if self._applying:
            logger.warning("[APPLY] 正在应用中，忽略本次请求")
            self.set_status("正在应用，请稍候…", STATUS_BUSY)
            return

        self._applying = True
        try:
            wallpaper = self.selected
            logger.info("[APPLY] id=%s, fps=%d", wallpaper.id, self.fps)

            cleaned = self._kill_existing()
            monitor = detect_monitor()
            if not monitor:
                logger.error("[APPLY] 显示器探测失败")
                self.set_status("错误: 无法探测显示器", STATUS_ERROR)
                return
            self.last_monitor = monitor

            args = [
                "--silent",
                "--no-audio-processing",
                "--disable-mouse",
                "--disable-parallax",
                "--disable-particles",
                "--fps", str(self.fps),
                "--screen-root", monitor,
                "--scaling", "fill",
                "--clamp", "border",
                *settings.notice_override(wallpaper.id),
                wallpaper.id,
            ]
            extra = f"（清理 {cleaned} 个进程）" if cleaned > 0 else ""
            self._spawn_and_verify(args, monitor, extra)
        finally:
            self._applying = False

    def _spawn_and_verify(self, args: list[str], monitor: str, extra: str) -> None:
        """起进程 → 等 2 秒 → 判存活 → 写状态。apply 只有这一条收尾路径。"""
        success, pid = start_detached(bin_path(ENGINE), args, ENGINE_LOG)
        if not success:
            logger.error("[APPLY] 启动 %s 失败", ENGINE)
            self.set_status(f"启动失败: {self.selected.id}", STATUS_ERROR)  # type: ignore[union-attr]
            return

        self._save_pid(pid)
        time.sleep(VERIFY_SECONDS)
        assert self.selected is not None
        if pid_alive(pid):
            self.last_apply_ok = True
            self.set_status(
                f"已加载 {self.selected.id}（{monitor}, pid={pid}）{extra}", STATUS_OK
            )
            return

        logger.error("[APPLY] 引擎启动后立即退出，pid=%d", pid)
        self.set_status(
            f"启动失败: {self.selected.id} — {tail_log(ENGINE_LOG)}", STATUS_ERROR
        )

    def stop(self) -> None:
        logger.info("[STOP] 停止壁纸")
        self.last_apply_ok = False
        cleaned = self._kill_existing()
        PID_FILE.unlink(missing_ok=True)
        extra = f"（清理 {cleaned} 个进程）" if cleaned > 0 else ""
        self.set_status(f"已停止壁纸{extra}", STATUS_IDLE)

    def cleanup_on_exit(self) -> None:
        if not self._stop_on_exit:
            logger.debug("[EXIT] stop_on_exit=False，退出时不清理壁纸")
            return
        logger.info("[EXIT] 退出清理壁纸")
        self._kill_existing()
        PID_FILE.unlink(missing_ok=True)

    # ---- 内部 ----

    def _save_pid(self, pid: int) -> None:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(pid))
        logger.debug("[PID] 记录 pid=%d", pid)

    def _kill_existing(self) -> int:
        cleaned = 0

        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
            except (ValueError, OSError):
                pid = 0
            if pid:
                logger.debug("[CLEAN] 结束 pid=%d", pid)
                stop_pid(pid)
                cleaned += 1
            PID_FILE.unlink(missing_ok=True)

        pkill = bin_path("pkill")
        subprocess.run([pkill, "-f", "[l]inux-wallpaperengine"], capture_output=True)
        for _ in range(10):
            if not self.is_running():
                break
            time.sleep(0.15)
        if self.is_running():
            logger.debug("[CLEAN] 仍有残留进程，使用 SIGKILL")
            subprocess.run([pkill, "-9", "-f", "[l]inux-wallpaperengine"], capture_output=True)

        if cleaned > 0:
            logger.info("[CLEAN] 通过 pid 文件清理 %d 个进程", cleaned)
        return cleaned
