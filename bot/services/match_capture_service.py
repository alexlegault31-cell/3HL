"""
Core logic behind the background match-capture system.

`capture_new_matches_for_club` is called by the periodic background loop
(see cogs/match_capture.py) -- it fetches a club's recent matches from
EA and archives any not already saved, using match_id as the dedup key.

`get_archived_matches_for_club` is called from stat_importer.py's
_find_matching_match -- it returns every archived match involving a
given club, normalized back into the same MatchDetail shape the live API
returns, so the two sources can be merged transparently.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import CapturedMatch
from bot.services.chelstats_client import ChelStatsClient, MatchDetail

log = logging.getLogger(__name__)


async def capture_new_matches_for_club(session: AsyncSession, client: ChelStatsClient, club_id: int) -> int:
    """Fetches this club's recent matches and archives any not already
    saved. Returns how many new matches were captured. Never raises --
    a capture failure for one club (or one API hiccup) should never stop
    the loop from continuing to the next club."""
    try:
        matches = await client.get_recent_club_matches(club_id)
    except Exception:  # noqa: BLE001
        log.warning("Match capture fetch failed for club %s", club_id, exc_info=True)
        return 0

    captured = 0
    for m in matches:
        existing = await session.scalar(select(CapturedMatch).where(CapturedMatch.match_id == m.match_id))
        if existing is not None:
            continue

        club_ids = list(m.raw.get("clubs", {}).keys())
        if len(club_ids) != 2:
            continue  # shouldn't happen given _normalize_match already validated this, but stay defensive

        session.add(
            CapturedMatch(
                match_id=m.match_id,
                club_id_a=int(club_ids[0]),
                club_id_b=int(club_ids[1]),
                ea_timestamp=m.timestamp,
                raw_payload=m.raw,
            )
        )
        captured += 1

    if captured:
        await session.flush()
    return captured


async def get_archived_matches_for_club(session: AsyncSession, club_id: int) -> list[MatchDetail]:
    """Every archived match involving this club, normalized back into a
    MatchDetail -- used as a fallback source alongside the live API call,
    so a match that has since scrolled out of EA's live window can still
    be found and imported."""
    rows = (
        await session.execute(
            select(CapturedMatch).where((CapturedMatch.club_id_a == club_id) | (CapturedMatch.club_id_b == club_id))
        )
    ).scalars().all()
    return [ChelStatsClient._normalize_match(row.raw_payload) for row in rows]
