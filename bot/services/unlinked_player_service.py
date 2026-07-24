"""Finds players who appeared in a just-imported game but haven't linked
their Discord account via /league player link yet -- lets a commissioner
immediately nudge the right people instead of discovering it later when
someone can't find their own stats."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import GoalieGameStat, Player, PlayerGameStat, Team, User


@dataclass
class UnlinkedPlayer:
    gamertag: str
    team_name: str


async def find_unlinked_players_in_game(session: AsyncSession, game_id: int) -> list[UnlinkedPlayer]:
    skater_rows = (await session.execute(select(PlayerGameStat).where(PlayerGameStat.game_id == game_id))).scalars().all()
    goalie_rows = (await session.execute(select(GoalieGameStat).where(GoalieGameStat.game_id == game_id))).scalars().all()

    # (player_id, team_id) pairs, deduped -- a player only ever plays for
    # one team in a given game, but skater/goalie tables are separate.
    seen: dict[int, int] = {}
    for line in (*skater_rows, *goalie_rows):
        seen[line.player_id] = line.team_id

    unlinked: list[UnlinkedPlayer] = []
    for player_id, team_id in seen.items():
        user = await session.scalar(select(User).where(User.player_id == player_id))
        if user is not None:
            continue  # already linked, nothing to flag
        player = await session.get(Player, player_id)
        team = await session.get(Team, team_id)
        if player is not None:
            unlinked.append(UnlinkedPlayer(gamertag=player.gamertag, team_name=team.name if team else "Unknown"))

    return unlinked
