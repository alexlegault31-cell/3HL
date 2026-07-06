"""
Thin async client around EA's real (undocumented, unofficial) Pro Clubs API.

CONFIRMED REAL ENDPOINT (as of July 2026)
------------------------------------------
"ChelStats"-style tools all pull directly from EA's own API at
proclubs.ea.com -- there is no separate hosted third-party backend to
point at. The real, currently-working call shape is:

    GET https://proclubs.ea.com/api/nhl/clubs/matches
        ?clubIds=<club_id>
        &platform=common-gen5
        &matchType=gameType5      (public/league matchmaking games)
        or matchType=club_private (privately-hosted lobby games)

This single endpoint returns full match history INCLUDING the complete
per-player box score for each match already -- there is no separate
"match detail" endpoint. An earlier version of this file assumed a
two-step summary-then-detail API shape that doesn't actually exist; this
version calls the one real endpoint and reuses its response for both
"which match is this" and "what's the box score."

EA's server also checks the `Referer` header and blocks requests that
don't set it to an ea.com origin -- every request below sends that.

IMPORTANT CAVEATS -- read before assuming a failure is a bug in this code
--------------------------------------------------------------------------
1. EA's `club_private` match-history endpoint (used for privately-hosted
   lobby games, which is how most organized leagues actually play their
   games) has been reported broken/unreliable by other developers across
   several NHL versions on EA's own forums -- independent of anything in
   this file. If your league plays private lobby matches and imports keep
   coming back with "no match found," try setting CHELSTATS_MATCH_TYPE to
   `gameType5` temporarily just to confirm the connection itself works,
   then investigate the private-match-specific issue separately.
2. EA's Pro Clubs API as a whole has had multi-week outages (one publicly
   reported as starting June 19, 2026). If every request fails the same
   way regardless of Club ID, check EA's own forums for current outage
   reports before assuming this code is broken.
3. This is unversioned and undocumented -- EA can change the response
   shape at any time with no notice. `_normalize_match` below is the only
   function that should need editing if the JSON shape drifts from what's
   assumed here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.config import settings

log = logging.getLogger(__name__)


@dataclass
class PlayerBoxScore:
    gamertag: str
    external_player_id: Optional[str]
    club_id: int
    is_goalie: bool

    # skater fields
    goals: int = 0
    assists: int = 0
    plus_minus: int = 0
    hits: int = 0
    pim: int = 0
    shots: int = 0
    ppg: int = 0

    # goalie fields
    shots_against: int = 0
    saves: int = 0
    goals_against: int = 0
    minutes_played: float = 0.0
    is_win: bool = False
    is_ot_loss: bool = False


@dataclass
class TeamBoxScore:
    club_id: int
    goals: int
    shots: int
    hits: int
    pim: int
    powerplay_goals: int = 0
    powerplay_opportunities: int = 0


@dataclass
class MatchDetail:
    match_id: str
    timestamp: int
    went_to_overtime: bool
    went_to_shootout: bool
    home: TeamBoxScore
    away: TeamBoxScore
    players: list[PlayerBoxScore]
    raw: dict = field(repr=False, default_factory=dict)


class ChelStatsError(RuntimeError):
    pass


class ChelStatsClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.chelstats_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.chelstats_api_key
        self.platform = settings.chelstats_platform
        self.match_type = settings.chelstats_match_type

    def _headers(self) -> dict:
        # EA's servers reject requests without an ea.com Referer -- this is
        # the single most common cause of a connection appearing to "not
        # work" against this API.
        headers = {"Accept": "application/json", "Referer": "https://www.ea.com"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession(headers=self._headers()) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 404:
                    return None
                if resp.status >= 400:
                    body = await resp.text()
                    raise ChelStatsError(f"GET {url} -> {resp.status}: {body[:300]}")
                return await resp.json()

    async def get_recent_club_matches(self, club_id: int, limit: Optional[int] = None) -> list[MatchDetail]:
        """Fetch a club's recent match history -- EA's real API returns
        each match's FULL box score already, so this doubles as both
        "what matches has this club played" and "what happened in them."
        """
        data = await self._get(
            "/clubs/matches",
            params={
                "clubIds": club_id,
                "platform": self.platform,
                "matchType": self.match_type,
            },
        )
        if not data:
            return []
        limit = limit or settings.chelstats_match_lookback
        matches = data if isinstance(data, list) else data.get("matches", [])
        normalized = [self._normalize_match(m) for m in matches]
        normalized.sort(key=lambda m: m.timestamp, reverse=True)
        return normalized[:limit]

    # ------------------------------------------------------------------
    # Normalization -- this is the one place to edit if EA's JSON shape
    # drifts from what's assumed here. Everything else in the bot works
    # against the MatchDetail dataclass, never raw provider JSON.
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_match(raw: dict) -> "MatchDetail":
        clubs = raw.get("clubs", {})
        club_ids = list(clubs.keys())
        if len(club_ids) != 2:
            raise ChelStatsError(f"Unexpected match shape, clubs={club_ids}")
        home_id, away_id = club_ids

        def team_box(cid: str) -> TeamBoxScore:
            c = clubs[cid]
            return TeamBoxScore(
                club_id=int(cid),
                goals=int(c.get("score", c.get("goals", 0))),
                shots=int(c.get("shots", 0)),
                hits=int(c.get("hits", 0)),
                pim=int(c.get("pim", 0)),
                powerplay_goals=int(c.get("ppg", 0)),
                powerplay_opportunities=int(c.get("ppOpportunities", 0)),
            )

        players: list[PlayerBoxScore] = []
        for cid, roster in raw.get("players", {}).items():
            for _, p in roster.items():
                is_goalie = str(p.get("position", "")).lower() in ("goalie", "g")
                players.append(
                    PlayerBoxScore(
                        gamertag=p.get("playername", p.get("persona", "Unknown")),
                        external_player_id=str(p.get("playerId")) if p.get("playerId") else None,
                        club_id=int(cid),
                        is_goalie=is_goalie,
                        goals=int(p.get("skgoals", 0)),
                        assists=int(p.get("skassists", 0)),
                        plus_minus=int(p.get("skplusmin", 0)),
                        hits=int(p.get("skhits", 0)),
                        pim=int(p.get("skpim", 0)),
                        shots=int(p.get("skshots", 0)),
                        ppg=int(p.get("skppg", 0)),
                        shots_against=int(p.get("glshots", 0)),
                        saves=int(p.get("glsaves", 0)),
                        goals_against=int(p.get("glga", 0)),
                        minutes_played=float(p.get("glmins", 0)) / 60.0 if p.get("glmins") else 0.0,
                        is_win=bool(int(p.get("glwins", 0))) if p.get("glwins") else False,
                        is_ot_loss=bool(int(p.get("otlosses", 0))) if p.get("otlosses") else False,
                    )
                )

        return MatchDetail(
            match_id=str(raw.get("matchId", raw.get("timestamp", ""))),
            timestamp=int(raw.get("timestamp", 0)),
            went_to_overtime=bool(raw.get("wentToOt", False)),
            went_to_shootout=bool(raw.get("wentToShootout", False)),
            home=team_box(home_id),
            away=team_box(away_id),
            players=players,
            raw=raw,
        )
