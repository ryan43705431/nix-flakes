"""路径与常量集中一处；环境变量开关也只在这里读一次。"""

from __future__ import annotations

import os
import re
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "lwe-gui-slint"
POSTER_DIR = CACHE_DIR / "previews"
ENGINE_LOG = CACHE_DIR / "engine.log"
PID_FILE = CACHE_DIR / "wallpaper.pid"

WORKSHOP_DIR = Path.home() / ".local/share/Steam/steamapps/workshop/content/431960"
ENGINE = "linux-wallpaperengine"

# nix 安装时 ui/ 在 $out/share/lwe-gui-slint/ui，由 wrapper 用 LWE_UI_DIR 指出；
# 开发时源码树里 ui/ 与 src/ 平级，走下面的推断值。
_SOURCE_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
UI_DIR = Path(os.environ.get("LWE_UI_DIR") or _SOURCE_UI_DIR)

# 抽帧或缩放策略变化时递增，让旧缓存自动失效
CACHE_VERSION = 2

# 列表缩略图宽度
THUMB_WIDTH = 320

# 作者开关
KEEP_NOTICE = bool(os.environ.get("LWE_KEEP_NOTICE"))
NOTICE_PATTERN = re.compile(r"提示框|prompt\s*box|notice", re.IGNORECASE)
