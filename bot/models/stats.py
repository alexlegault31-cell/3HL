
"""
Per-game box score rows. These are what `/player gamelog` reads, and what
`/game delete` must remove (along with reversing the aggregates they fed
into PlayerSeason / TeamSeason / StandingsEntry).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class PlayerGameStat(Base, IDMixin, TimestampMixin):
    __tablename__ = "player_stats"

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)

    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    plus_minus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pim: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ppg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    game: Mapped["Game"] = relationship()
    player: Mapped["Player"] = relationship()
    team: Mapped["Team"] = relationship()


class GoalieGameStat(Base, IDMixin, TimestampMixin):
    __tablename__ = "goalie_stats"

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)

    result: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=L,1=W,2=OTL
    shots_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minutes_played: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    shutout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    game: Mapped["Game"] = relationship()
    player: Mapped["Player"] = relationship()
    team: Mapped["Team"] = relationship()


class TeamGameStat(Base, IDMixin, TimestampMixin):
    """Team-level box score line (separate from Game.home_score/away_score
    so shots/PP/PK-style extended stats can be added later without
    touching the core Game table)."""

    __tablename__ = "team_stats"

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)

    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pim: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    powerplay_goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    powerplay_opportunities: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    game: Mapped["Game"] = relationship()
    team: Mapped["Team"] = relationship()

