"""
Player identity vs. season-scoped stats vs. team membership are kept as
three separate concepts:

  Player           -- the human / gamertag, season-independent
  PlayerSeason     -- cumulative season totals (GP, G, A, PTS, ...), one
                       row per player per season, updated incrementally as
                       each game is imported
  PlayerTeamLink   -- which team a player belonged to for a given season
                       (players can be traded/re-signed between seasons,
                       and in theory mid-season — link carries an
                       effective range so /team history stays accurate)
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class Player(Base, IDMixin, TimestampMixin):
    __tablename__ = "players"

    gamertag: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Cached EA/ChelStats numeric player id, when the provider exposes one.
    external_player_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    is_goalie: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[Optional["User"]] = relationship(back_populates="player", uselist=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Player {self.gamertag!r}>"


class PlayerTeamLink(Base, IDMixin, TimestampMixin):
    __tablename__ = "player_team_links"
    __table_args__ = (UniqueConstraint("player_id", "season_id", "team_id", name="uq_player_team_season"),)

    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)

    effective_from: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    player: Mapped["Player"] = relationship()
    team: Mapped["Team"] = relationship()
    season: Mapped["Season"] = relationship()


class PlayerSeason(Base, IDMixin, TimestampMixin):
    """Cumulative per-season stat line for a player, updated incrementally
    by the stat importer on every /entergame. Skater and goalie fields both
    live here (mutually exclusive in practice, gated by Player.is_goalie)
    to keep `/player stats` a single-row lookup."""

    __tablename__ = "player_seasons"
    __table_args__ = (UniqueConstraint("player_id", "season_id", name="uq_player_season"),)

    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    games_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- Skater totals ---
    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    plus_minus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pim: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ppg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # power play goals
    faceoffs_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    faceoffs_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    takeaways: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interceptions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_shots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    giveaways: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passes_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- Goalie totals ---
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ot_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shots_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shutouts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minutes_played: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    player: Mapped["Player"] = relationship()
    season: Mapped["Season"] = relationship()
    team: Mapped[Optional["Team"]] = relationship()

    @property
    def gaa(self) -> float:
        """Goals against average, per 60 minutes."""
        if self.minutes_played <= 0:
            return 0.0
        return round((self.goals_against / self.minutes_played) * 60, 2)

    @property
    def save_pct(self) -> float:
        if self.shots_against <= 0:
            return 0.0
        return round(self.saves / self.shots_against, 3)

    @property
    def faceoff_pct(self) -> float:
        total = self.faceoffs_won + self.faceoffs_lost
        if total <= 0:
            return 0.0
        return round(self.faceoffs_won / total, 3)

    @property
    def pass_pct(self) -> float:
        if self.pass_attempts <= 0:
            return 0.0
        return round(self.passes_completed / self.pass_attempts, 3)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlayerSeason player_id={self.player_id} season_id={self.season_id} pts={self.points}>"
