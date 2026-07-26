"""
Shared visual theme for every generated graphic. Centralizing this means
re-skinning the whole bot for a new league is a one-file change.

`prepare_canvas()` is the shared entry point every graphic now uses to
build its base image: if the league has set a custom background photo
(`/league admin add-background`), it fills the whole canvas (cropped to
fit, darkened so text stays readable). If not, it falls back to a
gradient banner in the league's accent color over a solid dark
background -- so every graphic looks good whether or not a background
photo is configured, and removing the background photo instantly reverts
to the built-in look with no other changes needed.

Font notes
----------
We ship no proprietary fonts. `FONT_DIR` defaults to the bundled
DejaVu fonts installed via the Dockerfile's `fonts-dejavu-core` package
(works out of the box, no licensing concerns). Drop a TTF named
`Bold.ttf` / `Regular.ttf` / `Black.ttf` into `assets/fonts/` to use a
custom league font instead -- `load_font()` prefers those if present.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

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
    # Base palette -- dark "broadcast graphics" look.
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

    @classmethod
    def team_color(cls, team, fallback=(88, 166, 255)):
        if team is not None and getattr(team, "primary_color", None):
            return hex_to_rgb(team.primary_color)
        return fallback


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return Theme.ACCENT
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))  # type: ignore[return-value]


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    """Masks the four corners of the final image into a rounded rectangle.
    Applied once at save time (not in prepare_canvas) since it needs to
    happen AFTER every graphic has finished drawing its content on top of
    the base canvas."""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (img.size[0] - 1, img.size[1] - 1)], radius=radius, fill=255)
    img.putalpha(mask)
    return img


def finalize_and_save(img: Image.Image, path, corner_radius: int = 20) -> None:
    """The one shared 'save' step every graphic should use instead of
    calling img.save() directly -- applies rounded corners universally so
    every graphic in the bot gets the same polished edge treatment from
    one place, rather than each file reimplementing it."""
    rounded = _round_corners(img, corner_radius)
    rounded.save(path)


def draw_soft_divider(draw: ImageDraw.ImageDraw, y: int, width: int, color: tuple[int, int, int], x_start: int = 0) -> None:
    """A divider line that fades out toward both ends instead of a hard
    solid bar all the way across -- reads as noticeably more polished on
    the highest-visibility graphics (standings, leaders board)."""
    span = width - x_start
    fade_zone = min(120, span // 3)
    for x in range(x_start, width):
        dist_from_edge = min(x - x_start, width - x)
        if dist_from_edge < fade_zone:
            t = dist_from_edge / fade_zone
        else:
            t = 1.0
        faded = _lerp_color(Theme.BG_DARK, color, t)
        draw.point((x, y), fill=faded)
        draw.point((x, y + 1), fill=faded)


async def prepare_canvas(
    width: int,
    height: int,
    accent_color: tuple[int, int, int] = Theme.ACCENT,
    background_url: Optional[str] = None,
    banner_height: Optional[int] = None,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Builds the base image + draw context every graphic starts from.

    If `background_url` is set and loads successfully, it fills the ENTIRE
    canvas (cropped to fit, darkened for text legibility) -- this is the
    optional custom background photo from `/league admin add-background`.

    Otherwise, falls back to a solid dark background with a gradient
    banner (dark navy -> the league's accent color) across the top
    `banner_height` pixels, plus a subtle radial glow for visual depth,
    which is the built-in look with no configuration needed.
    """
    if background_url:
        # Imported here (not at module top) to avoid a circular import,
        # since logo_fetch itself doesn't need anything from theme except
        # GENERATED_DIR.
        from bot.graphics.logo_fetch import get_background_image

        bg = await get_background_image(background_url, (width, height))
        if bg is not None:
            return bg, ImageDraw.Draw(bg)

    img = Image.new("RGB", (width, height), Theme.BG_DARK)
    draw = ImageDraw.Draw(img)

    if banner_height:
        dark_navy = (10, 14, 28)
        muted_accent = tuple(c // 3 for c in accent_color)
        for y in range(banner_height):
            t = (y / banner_height) * 0.6
            draw.line([(0, y), (width, y)], fill=_lerp_color(dark_navy, muted_accent, t))

        # Subtle radial glow in the upper-right (where the league logo
        # typically sits) -- adds real depth instead of a flat linear
        # fade, without being loud or distracting from the content below.
        glow_cx, glow_cy = int(width * 0.82), int(banner_height * 0.35)
        glow_radius = int(banner_height * 1.3)
        glow_layer = Image.new("RGB", (width, banner_height), (0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        for r in range(glow_radius, 0, -4):
            t = 1 - (r / glow_radius)
            glow_color = _lerp_color((0, 0, 0), accent_color, t * 0.35)
            glow_draw.ellipse(
                [(glow_cx - r, glow_cy - r), (glow_cx + r, glow_cy + r)],
                fill=glow_color,
            )
        banner_region = img.crop((0, 0, width, banner_height))
        blended = Image.blend(banner_region, glow_layer, 0.5)
        img.paste(blended, (0, 0))
        draw = ImageDraw.Draw(img)

        draw.rectangle([(0, banner_height - 4), (width, banner_height)], fill=accent_color)

    return img, draw
