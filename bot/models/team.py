
"""
`Team` is the franchise-level, season-independent identity (e.g. "Italy").
`TeamSeason` is the per-season participation row that actually carries the
linked Club ID (clubs/rosters can change across seasons, expansion teams
appear, etc.) and the season-scoped W/L/OTL/points/GF/GA used to build
standings.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class Team(Base, IDMixin, TimestampMixin):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # "#C8102E"
    secondary_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    seasons: Mapped[List["TeamSeason"]] = relationship(back_populates="team", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Team {self.name!r}>"


class TeamSeason(Base, IDMixin, TimestampMixin):
    """A team's participation + linked Club ID + record for one season."""

    __tablename__ = "team_seasons"
    __table_args__ = (
        UniqueConstraint("team_id", "season_id", name="uq_team_season"),
        UniqueConstraint("club_id", "season_id", name="uq_club_id_season"),
    )

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)

    # The EASHL/ChelStats Club ID linked for this team THIS season.
    club_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    club_name_cache: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ot_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Last 10 results as a string of "W"/"L"/"O", most recent last. Cheap to
    # store/update incrementally instead of recomputing from game history.
    streak_type: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)  # W/L/O
    streak_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_10: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    team: Mapped["Team"] = relationship(back_populates="seasons")
    season: Mapped["Season"] = relationship()

    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.ot_losses

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TeamSeason team_id={self.team_id} season_id={self.season_id} {self.wins}-{self.losses}-{self.ot_losses}>"

