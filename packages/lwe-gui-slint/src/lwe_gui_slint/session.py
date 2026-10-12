"""会话环境探测。

引擎与 hyprctl 都依赖几个环境变量，而程序不一定从会话终端启动
（systemd 单元、IDE、别的 shell 都可能缺），所以这里自己推断。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("lwe_gui_slint")


def _runtime_dir(env: dict[str, str]) -> Path:
    return Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def _newest_socket(runtime: Path, pattern: str) -> Path | None:
    try:
        candidates = [p for p in runtime.glob(pattern) if p.is_socket()]
    except OSError:
        return None
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def hypr_env() -> dict[str, str]:
    """hyprctl 需要 HYPRLAND_INSTANCE_SIGNATURE；没设就从 $XDG_RUNTIME_DIR/hypr 推断。"""
    env = os.environ.copy()
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return env
    socket = _newest_socket(_runtime_dir(env) / "hypr", "*/.socket.sock")
    if socket is not None:
        env["HYPRLAND_INSTANCE_SIGNATURE"] = socket.parent.name
    return env


def engine_env() -> dict[str, str]:
    """补齐引擎必需的会话环境。

    引擎要么走 Wayland、要么走 X11；判错的后果是 GLFW 报
    "Failed to detect any supported platform" 直接退出。父进程不一定带着
    WAYLAND_DISPLAY，所以自己从 $XDG_RUNTIME_DIR/wayland-* 推断。
    """
    env = hypr_env()
    if not env.get("WAYLAND_DISPLAY"):
        socket = _newest_socket(_runtime_dir(env), "wayland-*")
        if socket is not None:
            env["WAYLAND_DISPLAY"] = socket.name

    if env.get("WAYLAND_DISPLAY"):
        env["XDG_SESSION_TYPE"] = "wayland"
    elif env.get("DISPLAY"):
        env.setdefault("XDG_SESSION_TYPE", "x11")
    return env


def detect_monitor() -> str:
    """读 hyprctl -j monitors，返回第一个合法显示器名。

    不要解析文本输出：hyprctl 失败时会打印
    "HYPRLAND_INSTANCE_SIGNATURE not set! (...)"，取第二列会拿到字符串 "not"。
    """
    try:
        result = subprocess.run(
            [shutil.which("hyprctl") or "hyprctl", "-j", "monitors"],
            capture_output=True, text=True, env=hypr_env(), timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("[MONITOR] hyprctl 调用失败: %s", exc)
        return ""

    try:
        monitors = json.loads(result.stdout)
    except (ValueError, TypeError):
        logger.error(
            "[MONITOR] 无法解析 hyprctl 输出: %s", (result.stdout or result.stderr)[:120]
        )
        return ""

    for entry in monitors if isinstance(monitors, list) else []:
        name = str(entry.get("name") or "").strip()
        if name and all(ch.isalnum() or ch in "._-" for ch in name):
            return name
    logger.error("[MONITOR] 未找到可用显示器")
    return ""
