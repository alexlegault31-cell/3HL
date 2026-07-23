"""
A `PlayoffSeries` is one best-of-N matchup within a single-elimination
bracket round (e.g. "Round 1, Series 2: Italy vs France, best of 5").

Bracket structure is implicit rather than a separate "bracket" table:
`round_order` (1, 2, 3, ...) plus `series_order` within that round is
enough to reconstruct the whole tree, and `/league admin advance-round`
pairs adjacent series_order values (1&2 -> next round's series 1, 3&4 ->
next round's series 2, etc.) which is how standard single-elimination
brackets propagate.

`ScheduleGame.playoff_series_id` links individual games to the series
they count toward; `wins_a`/`wins_b` are updated by
`services/playoff_service.py` every time a linked game is imported or
forfeited, and `winner_team_id` is set once a team reaches a series-
clinching majority of `best_of`.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class PlayoffSeries(Base, IDMixin, TimestampMixin):
    __tablename__ = "playoff_series"

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    round_name: Mapped[str] = mapped_column(String(64), nullable=False)  # "Round 1", "Semifinals", "Finals"
    round_order: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3... for bracket propagation
    series_order: Mapped[int] = mapped_column(Integer, nullable=False)  # position within the round

    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    seed_a: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seed_b: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    best_of: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    wins_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    winner_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    season: Mapped["Season"] = relationship()
    team_a: Mapped["Team"] = relationship(foreign_keys=[team_a_id])
    team_b: Mapped["Team"] = relationship(foreign_keys=[team_b_id])
    winner_team: Mapped[Optional["Team"]] = relationship(foreign_keys=[winner_team_id])

    @property
    def wins_needed(self) -> int:
        return (self.best_of // 2) + 1

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlayoffSeries {self.round_name} #{self.series_order}: {self.wins_a}-{self.wins_b}>"
