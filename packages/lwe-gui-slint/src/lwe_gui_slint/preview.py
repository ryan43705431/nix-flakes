"""列表缩略图：把素材抽成一帧静态图并缓存。

Slint 不自带 GIF 与视频解码（遇到 GIF 直接报
"The image format Gif is not supported"），所以视频与动图要先抽一帧。
已经是 PNG/JPEG 的素材直接返回原文件。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from lwe_gui_slint.config import CACHE_VERSION, POSTER_DIR

logger = logging.getLogger("lwe_gui_slint")

STATIC_SUFFIXES = {".png", ".jpg", ".jpeg"}
FFMPEG = shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return FFMPEG is not None


def _run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(command, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("ffmpeg 执行失败: %s", exc)
        return None


def _stamp(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def poster(source: Path | None, width: int) -> Path | None:
    """返回 Slint 可直接加载的图片路径；失败返回 None。

    PNG/JPEG 直接返回原文件，其余（视频、GIF、WebP）抽第一帧，且**不放大**。
    """
    if source is None or not source.exists():
        return None
    if source.suffix.lower() in STATIC_SUFFIXES:
        return source
    if FFMPEG is None:
        logger.warning("未找到 ffmpeg，无法为 %s 生成缩略图", source.name)
        return None

    target = (
        POSTER_DIR / f"v{CACHE_VERSION}_{source.parent.name}_{source.name}_{width}_{_stamp(source)}.png"
    )
    if target.exists():
        return target

    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    work = target.with_name(target.name + ".part.png")
    result = _run([
        FFMPEG, "-v", "error", "-y", "-i", str(source),
        "-frames:v", "1", "-vf", f"scale='min({width},iw)':-2", str(work),
    ])
    if result is None or result.returncode != 0 or not work.exists():
        logger.warning("抽首帧失败 %s", source.name)
        work.unlink(missing_ok=True)
        return None
    os.replace(work, target)
    return target
