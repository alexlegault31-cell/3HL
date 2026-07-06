
"""Small embed-building helpers shared across cogs, kept consistent so the
bot has one visual identity in plain-text/embed responses (graphics handle
the heavier visual lifting via bot/graphics/*)."""
from __future__ import annotations

import discord

BRAND_COLOR = discord.Color.from_rgb(88, 166, 255)
SUCCESS_COLOR = discord.Color.from_rgb(62, 207, 142)
ERROR_COLOR = discord.Color.from_rgb(235, 87, 87)


def info_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=BRAND_COLOR)


def success_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=description, color=SUCCESS_COLOR)


def error_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"❌ {title}", description=description, color=ERROR_COLOR)

