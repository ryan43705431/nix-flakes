"""LWE Wallpaper Manager —— Python + Slint 实现。

窗口里只有一个壁纸列表和一条底部信息栏：选中、调帧率、应用 / 停止。
引擎进程在 `engine.py`，素材缩略图在 `preview.py`，作者开关在 `settings.py`。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import slint

from lwe_gui_slint import model as model_module, preview
from lwe_gui_slint.config import CACHE_DIR, THUMB_WIDTH, UI_DIR
from lwe_gui_slint.engine import STATUS_BUSY, STATUS_IDLE, WallpaperEngine

logger = logging.getLogger("lwe_gui_slint")


def setup_logging() -> None:
    level = logging.DEBUG if os.environ.get("LWE_DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def load_image(path: Path | None) -> slint.Image:
    """把磁盘图片转成 Slint 的 image 属性值；失败时返回空图。

    注意：`slint.Image` 被 pyo3 标记为 unsendable，**不能跨线程传递**，
    所以这个函数只能在主线程调用。
    """
    if path is None:
        return slint.Image()
    try:
        return slint.Image.load_from_path(str(path))
    except RuntimeError as exc:
        logger.warning("图片加载失败 %s: %s", path, exc)
        return slint.Image()


def thumbnail_for(wallpaper: model_module.Wallpaper) -> Path | None:
    """列表缩略图：作者封面图 > 主素材首帧。

    封面图是作者挑的代表帧，比视频首帧亮、也更有代表性。
    """
    return preview.poster(wallpaper.cover, THUMB_WIDTH) or preview.poster(
        wallpaper.source, THUMB_WIDTH
    )


def build_rows(library: list[model_module.Wallpaper]) -> list[dict]:
    """在工作线程里跑：只算路径与抽帧，不创建任何 Slint 对象。"""
    return [
        {
            "id": wallpaper.id,
            "title": wallpaper.title,
            "type": wallpaper.type,
            "kind": wallpaper.kind,
            "thumb": thumbnail_for(wallpaper),
        }
        for wallpaper in library
    ]


def main() -> int:
    setup_logging()
    if not preview.ffmpeg_available():
        logger.warning("未找到 ffmpeg：动图与视频壁纸将没有缩略图")

    components = slint.load_file(UI_DIR / "main.slint")
    window = components.AppWindow()
    engine = WallpaperEngine()

    library: list[model_module.Wallpaper] = []
    loop: asyncio.AbstractEventLoop | None = None

    def apply_status(kind: str, text: str) -> None:
        window.status = text
        window.status_kind = kind

    async def refresh_library() -> None:
        nonlocal library
        engine.set_status("正在扫描壁纸库…", STATUS_BUSY)
        library = await asyncio.to_thread(model_module.scan)
        rows = await asyncio.to_thread(build_rows, library)
        window.wallpapers = slint.ListModel(
            [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "type": row["type"],
                    "kind": row["kind"],
                    "thumb": load_image(row["thumb"]),
                }
                for row in rows
            ]
        )
        engine.set_status(f"共 {len(library)} 张壁纸", STATUS_IDLE)

    def on_select(index: int) -> None:
        if not 0 <= index < len(library):
            return
        wallpaper = library[index]
        engine.select(wallpaper)
        window.current_index = index
        window.title_text = wallpaper.title
        window.id_text = wallpaper.id
        window.type_text = wallpaper.type

    async def run_blocking(action) -> None:
        window.busy = True
        try:
            await asyncio.to_thread(action)
        finally:
            window.busy = False

    def on_apply() -> None:
        assert loop is not None
        loop.create_task(run_blocking(engine.apply))
        loop.create_task(recheck_alive())

    async def recheck_alive() -> None:
        await asyncio.sleep(5)
        await asyncio.to_thread(engine.recheck_alive)

    def on_stop() -> None:
        assert loop is not None
        loop.create_task(run_blocking(engine.stop))

    def on_fps(value: int) -> None:
        engine.set_fps(value)
        window.fps = engine.fps

    async def bootstrap(component) -> None:
        nonlocal loop
        loop = asyncio.get_running_loop()

        def post_status(kind: str, text: str) -> None:
            """可能从工作线程调用，投递回主线程改属性。"""
            assert loop is not None
            loop.call_soon_threadsafe(apply_status, kind, text)

        engine.set_notify(post_status)
        component.select = on_select
        component.apply = on_apply
        component.stop = on_stop
        component.fps_changed = on_fps
        apply_status(engine.status_kind, engine.status)
        await refresh_library()
        logger.info("界面就绪，缓存目录 %s", CACHE_DIR)

    window.show()
    try:
        slint.run_event_loop(bootstrap(window))
    finally:
        engine.cleanup_on_exit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
