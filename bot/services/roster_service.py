"""Roster query for the club stats card -- every player who's played at
least one game for this team this season, split into skaters and
goalies since they show different stat columns.

Built directly from PlayerGameStat/GoalieGameStat (real per-game rows),
NOT from Player.is_goalie -- that flag reflects whichever role a player
most recently played and gets overwritten on every import, so a player
who's genuinely played both roles this season (subbing, filling in
shorthanded, etc.) would otherwise only ever show up in one of the two
tables, with their other role's real, recorded stats invisible."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Game, GoalieGameStat, Player, PlayerGameStat, ScheduleGame


@dataclass
class RosterSkaterRow:
    gamertag: str
    games_played: int
    goals: int
    assists: int
    points: int
    ppg: float


@dataclass
class RosterGoalieRow:
    gamertag: str
    games_played: int
    goals_against: int
    gaa: float
    saves: int
    save_pct: float
    shutouts: int


async def get_team_roster(session: AsyncSession, team_id: int, season_id: int) -> tuple[list[RosterSkaterRow], list[RosterGoalieRow]]:
    """Returns (skaters, goalies) -- only players with at least one game
    played for this team this season in that specific role, sorted by
    points/GAA respectively. A player with real games in both roles this
    season correctly appears in both lists."""
    skater_rows = (
        await session.execute(
            select(PlayerGameStat, Player)
            .join(Player, Player.id == PlayerGameStat.player_id)
            .join(Game, Game.id == PlayerGameStat.game_id)
            .join(ScheduleGame, ScheduleGame.game_id == Game.id)
            .where(ScheduleGame.season_id == season_id, PlayerGameStat.team_id == team_id)
        )
    ).all()

    goalie_rows = (
        await session.execute(
            select(GoalieGameStat, Player)
            .join(Player, Player.id == GoalieGameStat.player_id)
            .join(Game, Game.id == GoalieGameStat.game_id)
            .join(ScheduleGame, ScheduleGame.game_id == Game.id)
            .where(ScheduleGame.season_id == season_id, GoalieGameStat.team_id == team_id)
        )
    ).all()

    skater_by_player: dict[int, list] = {}
    for line, player in skater_rows:
        skater_by_player.setdefault(player.id, (player, []))[1].append(line)

    goalie_by_player: dict[int, list] = {}
    for line, player in goalie_rows:
        goalie_by_player.setdefault(player.id, (player, []))[1].append(line)

    skaters = []
    for player, lines in skater_by_player.values():
        gp = len(lines)
        goals = sum(l.goals for l in lines)
        assists = sum(l.assists for l in lines)
        points = sum(l.points for l in lines)
        skaters.append(
            RosterSkaterRow(
                gamertag=player.gamertag,
                games_played=gp,
                goals=goals,
                assists=assists,
                points=points,
                ppg=(points / gp) if gp else 0.0,
            )
        )

    goalies = []
    for player, lines in goalie_by_player.values():
        gp = len(lines)
        total_sa = sum(l.shots_against for l in lines)
        total_sv = sum(l.saves for l in lines)
        total_ga = sum(l.goals_against for l in lines)
        total_min = sum(l.minutes_played for l in lines)
        goalies.append(
            RosterGoalieRow(
                gamertag=player.gamertag,
                games_played=gp,
                goals_against=total_ga,
                gaa=(total_ga / (total_min / 60)) if total_min else 0.0,
                saves=total_sv,
                save_pct=(total_sv / total_sa) if total_sa else 0.0,
                shutouts=sum(1 for l in lines if l.shutout),
            )
        )

    skaters.sort(key=lambda r: r.points, reverse=True)
    goalies.sort(key=lambda r: r.gaa)
    return skaters, goalies
