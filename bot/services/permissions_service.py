
"""
Permission tiers, per the spec:
  Commissioner -> full control
  GM           -> team-related functions (roster moves, /entergame for own
                   team, forfeits, schedule edits scoped to GM duties)
  Player       -> view stats, link account, view schedules

Implemented as Discord role-name checks (configurable via .env), kept as
plain functions (not decorators tied 1:1 to commands) so cogs can compose
them with extra logic (e.g. "GM OR it's their own team").
"""
from __future__ import annotations

import discord

from bot.config import settings


def is_commissioner(member: discord.Member) -> bool:
    return any(r.name == settings.role_commissioner for r in member.roles) or member.guild_permissions.administrator


def is_gm(member: discord.Member) -> bool:
    return is_commissioner(member) or any(r.name == settings.role_gm for r in member.roles)


class PermissionDenied(Exception):
    def __init__(self, required: str):
        self.required = required
        super().__init__(f"This command requires the {required} role.")


def require_commissioner(member: discord.Member) -> None:
    if not is_commissioner(member):
        raise PermissionDenied(settings.role_commissioner)


def require_gm(member: discord.Member) -> None:
    if not is_gm(member):
        raise PermissionDenied(f"{settings.role_gm} or {settings.role_commissioner}")

