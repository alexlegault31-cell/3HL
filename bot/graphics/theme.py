################################################################
FILE PATH TO TYPE ON GITHUB: bot/graphics/theme.py
################################################################
"""
Shared visual theme for every generated graphic. Centralizing this means
re-skinning the whole bot for a new league is a one-file change.

Font notes
----------
We ship no proprietary fonts. `FONT_DIR` defaults to the bundled
DejaVu fonts installed via the Dockerfile's `fonts-dejavu-core` package
(works out of the box, no licensing concerns). Drop a TTF named
`Bold.ttf` / `Regular.ttf` / `Black.ttf` into `assets/fonts/` to use a
custom league font instead — `load_font()` prefers those if present.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
BG_DIR = ASSETS_DIR / "backgrounds"
GENERATED_DIR = Path(os.environ.get("GENERATED_DIR", Path(__file__).resolve().parent.parent.parent / "generated"))
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

_SYSTEM_FALLBACKS = {
    "Black": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "Mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}


@lru_cache(maxsize=64)
def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    custom = FONT_DIR / f"{weight}.ttf"
    path = str(custom) if custom.exists() else _SYSTEM_FALLBACKS.get(weight, _SYSTEM_FALLBACKS["Regular"])
    return ImageFont.truetype(path, size)


class Theme:
    # Base palette — dark "broadcast graphics" look.
    BG_DARK = (16, 18, 24)
    BG_PANEL = (24, 27, 36)
    BG_PANEL_ALT = (30, 34, 45)
    BORDER = (52, 58, 74)

    TEXT_PRIMARY = (240, 242, 247)
    TEXT_SECONDARY = (158, 165, 184)
    TEXT_MUTED = (104, 110, 128)

    ACCENT = (88, 166, 255)
    WIN_GREEN = (62, 207, 142)
    LOSS_RED = (235, 87, 87)
    GOLD = (245, 197, 66)
    SILVER = (192, 197, 206)
    BRONZE = (205, 138, 89)

    @staticmethod
    def team_color(team, fallback=(88, 166, 255)):
        if getattr(team, "primary_color", None):
            return hex_to_rgb(team.primary_color)
        return fallback


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return Theme.ACCENT
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

===== END OF FILE, COPY UP TO HERE =====
