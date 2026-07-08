"""
Fetches and caches team logo images from `Team.logo_url` (set via
`/league club add-logo`), so graphics can draw a real crest instead of a
plain colored dot.

Design notes
------------
- Cached to disk under `generated/logo_cache/`, keyed by a hash of the
  URL (not the team id) -- if a team's logo URL changes, it's treated as
  a fresh cache entry automatically rather than serving a stale image.
- Every call is wrapped so a bad URL, timeout, or corrupt image falls
  back to `None` rather than raising -- graphics code always has a
  colored-dot fallback ready and should never crash because a logo
  failed to load.
- Resizing to the caller's exact target size happens on every call
  (cheap, since it's operating on an already-downloaded small image) so
  one cached original can serve differently-sized graphics.
"""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Optional

import aiohttp
from PIL import Image

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
                    log.warning("Logo fetch failed (%s) for %s", resp.status, url)
                    return None
                data = await resp.read()
    except Exception:  # noqa: BLE001
        log.warning("Logo fetch failed for %s", url, exc_info=True)
        return None

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # confirms it's actually a valid image, raises otherwise
        # Re-open after verify() -- verify() leaves the file object unusable
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img.save(cache_path, format="PNG")
        return cache_path
    except Exception:  # noqa: BLE001
        log.warning("Logo data was not a valid image for %s", url, exc_info=True)
        return None


async def get_team_logo(logo_url: Optional[str], size: tuple[int, int]) -> Optional[Image.Image]:
    """Returns a resized RGBA PIL Image for the given logo URL, or None if
    there's no URL, the fetch failed, or the image was invalid. Callers
    should always have a colored-dot/text fallback for the None case."""
    if not logo_url:
        return None

    cache_path = await _download_and_cache(logo_url)
    if cache_path is None:
        return None

    try:
        img = Image.open(cache_path).convert("RGBA")
        img = img.resize(size, Image.LANCZOS)
        return img
    except Exception:  # noqa: BLE001
        log.warning("Failed to load cached logo %s", cache_path, exc_info=True)
        return None
