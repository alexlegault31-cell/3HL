"""
Runs continuously in the background, independent of any command --
periodically checks EA's API for every club currently registered to an
active season, and archives any new matches it sees. This is what
protects against a busy multi-game night (with lagouts) pushing an
earlier game out of EA's own "last ~5 games" window before someone gets
around to running /league admin submit-game for it.

A deliberately conservative interval and a small delay between each
club's request -- this hits EA's same undocumented, unofficial API as
everything else in this bot, and there's no reason to hammer it any
harder than necessary just because this runs on a timer instead of a
command.
"""
from __future__ import annotations

import asyncio
import logging

from discord.ext import commands, tasks
from sqlalchemy import select

from bot.database import get_session
from bot.models import Team, TeamSeason
from bot.services.chelstats_client import ChelStatsClient
from bot.services.match_capture_service import capture_new_matches_for_club
from bot.services.season_service import SeasonNotFound, get_active_season

log = logging.getLogger(__name__)

CAPTURE_INTERVAL_MINUTES = 10
DELAY_BETWEEN_CLUBS_SECONDS = 2


class MatchCaptureCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.client = ChelStatsClient()
        self.capture_loop.start()

    def cog_unload(self) -> None:
        self.capture_loop.cancel()

    @tasks.loop(minutes=CAPTURE_INTERVAL_MINUTES)
    async def capture_loop(self) -> None:
        async with get_session() as session:
            try:
                season = await get_active_season(session)
            except SeasonNotFound:
                return

            club_ids: set[int] = set(
                (
                    await session.execute(
                        select(TeamSeason.club_id)
                        .join(Team, Team.id == TeamSeason.team_id)
                        .where(TeamSeason.season_id == season.id, Team.is_active.is_(True), TeamSeason.club_id.is_not(None))
                    )
                ).scalars().all()
            )
            if not club_ids:
                return

            total_captured = 0
            for club_id in club_ids:
                count = await capture_new_matches_for_club(session, self.client, club_id)
                total_captured += count
                await asyncio.sleep(DELAY_BETWEEN_CLUBS_SECONDS)

            if total_captured:
                log.info("Match capture: archived %d new match(es) across %d club(s)", total_captured, len(club_ids))

    @capture_loop.before_loop
    async def before_capture_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MatchCaptureCog(bot))
