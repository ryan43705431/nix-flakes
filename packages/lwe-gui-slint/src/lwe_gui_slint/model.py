"""扫描 Steam 创意工坊里的 Wallpaper Engine 壁纸目录。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("lwe_gui_slint")

WORKSHOP_DIR = Path.home() / ".local/share/Steam/steamapps/workshop/content/431960"

KIND_IMAGE = "image"
KIND_ANIMATED = "animated"
KIND_VIDEO = "video"


@dataclass(slots=True)
class Wallpaper:
    id: str
    title: str
    type: str
    kind: str
    source: Path | None
    cover: Path | None = None


def scan(workshop: Path = WORKSHOP_DIR) -> list[Wallpaper]:
    """读取创意工坊目录，返回按数字 id 排序的壁纸列表。"""
    if not workshop.is_dir():
        logger.warning("创意工坊目录不存在: %s", workshop)
        return []

    items: list[Wallpaper] = []
    for folder in sorted(
        workshop.iterdir(),
        key=lambda p: int(p.name) if p.name.isdigit() else 0,
    ):
        if not folder.is_dir():
            continue
        project = folder / "project.json"
        if not project.exists():
            continue
        try:
            data = json.loads(project.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("跳过 %s: project.json 无法解析 (%s)", folder.name, exc)
            continue

        source, kind = find_preview(folder)
        items.append(
            Wallpaper(
                id=folder.name,
                title=str(data.get("title") or "<无标题>"),
                type=str(data.get("type") or "unknown"),
                kind=kind,
                source=source,
                cover=find_cover(folder),
            )
        )

    logger.info("扫描到 %d 张壁纸", len(items))
    return items


def find_preview(folder: Path) -> tuple[Path | None, str]:
    """挑预览素材：视频 > 静态图 > 动图。

    原 lwe-gui 把 preview.gif 排在视频前面，而创意工坊里的 gif 往往只有 160–256px，
    同目录的 mp4 却是 1080p/4K。照搬会把小图铺满整屏，放大 5 倍必然发糊。
    """
    videos: list[Path] = []
    for ext in ("mp4", "webm"):
        videos.extend(folder.glob(f"*.{ext}"))
    if videos:
        videos.sort(key=lambda p: (0 if "preview" in p.name.lower() else 1, p.name))
        return videos[0], KIND_VIDEO

    for ext in ("png", "jpg", "jpeg", "webp"):
        candidate = folder / f"preview.{ext}"
        if candidate.exists():
            return candidate, KIND_IMAGE

    for name in ("preview.gif", "preview.webp"):
        candidate = folder / name
        if candidate.exists():
            return candidate, KIND_ANIMATED

    return None, KIND_IMAGE


def find_cover(folder: Path) -> Path | None:
    """作者提供的封面图（preview.png/jpg/webp）。

    列表缩略图只有 44×28，用小尺寸下更亮、更有代表性的封面图，
    比拿视频首帧（常常是暗场或淡入第一帧）效果好得多。
    """
    for ext in ("png", "jpg", "jpeg", "webp"):
        candidate = folder / f"preview.{ext}"
        if candidate.exists():
            return candidate
    return None
