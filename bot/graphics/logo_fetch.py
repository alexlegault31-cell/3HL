"""
Fetches and caches images from URLs -- both team/league logos (drawn as-is,
small) and full-canvas background images (cropped to fill, then darkened
so text stays readable on top of them).
"""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Optional

import aiohttp
from PIL import Image, ImageEnhance

from bot.graphics.theme import GENERATED_DIR

log = logging.getLogger(__name__)

LOGO_CACHE_DIR = GENERATED_DIR / "logo_cache"
LOGO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_FETCH_TIMEOUT_SECONDS = 8


def _cache_path_for_url(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return LOGO_CACHE_DIR / f"{digest}.png"


async def _download_and_cache(url: str) -> Optional[Path]:
    cache_path = _cache_path_for_url(url)
    if cache_path.exists():
        return cache_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=_FETCH_TIMEOUT_SECONDS)) as resp:
                if resp.status != 200:
                    log.warning("Image fetch failed (%s) for %s", resp.status, url)
                    return None
                data = await resp.read()
    except Exception:
        log.warning("Image fetch failed for %s", url, exc_info=True)
        return None

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img.save(cache_path, format="PNG")
        return cache_path
    except Exception:
        log.warning("Image data was not a valid image for %s", url, exc_info=True)
        return None


async def get_team_logo(logo_url: Optional[str], size: tuple[int, int]) -> Optional[Image.Image]:
    """Returns a resized RGBA image for a team/league logo, or None on any
    failure. Callers should always have a colored-shape fallback ready."""
    if not logo_url:
        return None
    cache_path = await _download_and_cache(logo_url)
    if cache_path is None:
        return None
    try:
        img = Image.open(cache_path).convert("RGBA")
        return img.resize(size, Image.LANCZOS)
    except Exception:
        log.warning("Failed to load cached logo %s", cache_path, exc_info=True)
        return None


async def get_background_image(
    background_url: Optional[str], size: tuple[int, int], darken: float = 0.45
) -> Optional[Image.Image]:
    """Returns a full-canvas background image cropped (not stretched) to
    exactly fill `size`, with a dark overlay applied so text drawn on top
    stays readable. Returns None if no URL is set or the fetch/crop fails
    -- callers fall back to the plain gradient/solid background in that
    case, so a bad background URL never breaks the graphic."""
    if not background_url:
        return None
    cache_path = await _download_and_cache(background_url)
    if cache_path is None:
        return None
    try:
        img = Image.open(cache_path).convert("RGB")

        # Crop-to-fill (like CSS background-size: cover) -- resize so the
        # SHORTER dimension matches the target, then center-crop the rest.
        target_w, target_h = size
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w, new_h = int(src_w * scale) + 1, int(src_h * scale) + 1
        img = img.resize((new_w, new_h), Image.LANCZOS)

        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))

        # Darken so white/light text stays readable on top of any photo.
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.0 - darken)

        return img.convert("RGB")
    except Exception:
        log.warning("Failed to load/crop background %s", cache_path, exc_info=True)
        return None
