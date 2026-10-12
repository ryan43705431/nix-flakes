"""作者在工程里暴露的开关。

Wallpaper Engine 的场景壁纸把设置项写在 project.json 的
`general.properties` 里；带 `user` 标记的才是「用户设置」。
「提示框」这类开关没有该标记，只能按标签识别。
"""

from __future__ import annotations

import json
import logging

from lwe_gui_slint.config import KEEP_NOTICE, NOTICE_PATTERN, WORKSHOP_DIR

logger = logging.getLogger("lwe_gui_slint")


def _properties(wallpaper_id: str) -> dict:
    project = WORKSHOP_DIR / wallpaper_id / "project.json"
    try:
        data = json.loads(project.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return (data.get("general", {}) or {}).get("properties") or {}


def notice_key(wallpaper_id: str) -> str | None:
    """找「提示框」开关的属性名。

    键名逐张不同，实测有 `fontcolorff4848bigbpromptbox`、`bigb`，
    还有一张键名是乱的 `brbbrbreathinganimation` 但标签写着「🔘提示框 Prompt Box」，
    所以必须按标签匹配，不能写死键名。
    """
    for key, prop in _properties(wallpaper_id).items():
        if not isinstance(prop, dict):
            continue
        if prop.get("type") not in ("bool", "boolean"):
            continue
        if NOTICE_PATTERN.search(str(prop.get("text", ""))):
            return key
    return None


def has_notice(wallpaper_id: str) -> bool:
    return notice_key(wallpaper_id) is not None


def notice_override(wallpaper_id: str) -> list[str]:
    """返回关掉提示框所需的引擎参数。

    作者自己在壁纸里写明「此提示框可在用户设置永久关闭」，这里替他执行；
    想保留原样设 `LWE_KEEP_NOTICE=1`。
    """
    if KEEP_NOTICE:
        return []
    key = notice_key(wallpaper_id)
    if key is None:
        return []
    logger.info("[NOTICE] 关闭作者提示框 %s", key)
    return ["--set-property", f"{key}=0"]
