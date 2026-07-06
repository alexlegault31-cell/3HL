Thin async client around the ChelStats / ChelHead EASHL stats API.

IMPORTANT — read before deploying
----------------------------------
"ChelStats" and "ChelHead" are community projects that scrape/mirror EA's
internal (undocumented, unofficial, and historically unstable) EASHL club
stats API. Their exact endpoint shapes change over time and neither
exposes a single, stable, publicly documented contract the way a normal
SaaS API would.

Rather than hard-coding endpoint paths that may be stale by the time you
deploy this, this client is built as a thin, swappable adapter:

  * `ChelStatsClient` defines the *interface* the rest of the bot relies on
    (`get_recent_club_matches`, `get_match_detail`).
  * `_normalize_match_summary` / `_normalize_match_detail` are the ONLY
    places that need to change if the upstream JSON shape differs from
    what's assumed here — everything downstream (stat_importer.py) works
    against the normalized dataclasses, not raw provider JSON.
  * Set `CHELSTATS_BASE_URL` in `.env` to whichever mirror you're using.
    If you're instead scraping the EA NHL companion API directly, point
    this client's `base_url` there and adjust the two normalize functions
    — nothing else in the codebase needs to change.

Matching a scheduled game to a played EASHL match
--------------------------------------------------
EASHL doesn't know about your league's schedule — it just knows two clubs
played a match at some timestamp. `stat_importer.py` calls
`get_recent_club_matches()` for BOTH linked Club IDs, intersects on match
id, and picks the most recent unimported one as the candidate for
`/entergame`. This is why every club's `CHELSTATS_MATCH_LOOKBACK` recent
matches are fetched rather than just the single latest one — coordinating
two different stats endpoints' "latest match" is unreliable in practice
(e.g. if a club plays an exhibition + a league game close together).
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
class MatchSummary:
    """Normalized "one row in a club's match history" result."""

    match_id: str
    timestamp: int  # unix epoch seconds
    club_id_home: int
    club_id_away: int
    score_home: int
    score_away: int
    raw: dict = field(repr=False, default_factory=dict)


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

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
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

    async def get_recent_club_matches(self, club_id: int, limit: Optional[int] = None) -> list[MatchSummary]:
        """Fetch a club's recent EASHL match history.

        Expected upstream shape (ChelStats-style):
            GET /clubs/{club_id}/matches?platform=common-gen5&limit=20
            -> {"matches": [{ "matchId": "...", "timestamp": 169..., 
                               "clubs": {"<club_id>": {...}, "<opp_id>": {...}} }, ...]}
        """
        limit = limit or settings.chelstats_match_lookback
        data = await self._get(
            f"/clubs/{club_id}/matches",
            params={"platform": self.platform, "limit": limit},
        )
        if not data:
            return []
        return [self._normalize_match_summary(m) for m in data.get("matches", [])]

    async def get_match_detail(self, match_id: str, club_id: int) -> Optional[MatchDetail]:
        """Fetch the full box score for a single match.

        Expected upstream shape (ChelStats-style):
            GET /matches/{match_id}?clubId={club_id}&platform=common-gen5
            -> {"matchId": ..., "timestamp": ..., "clubs": {...}, "players": {...}}
        """
        data = await self._get(
            f"/matches/{match_id}",
            params={"clubId": club_id, "platform": self.platform},
        )
        if not data:
            return None
        return self._normalize_match_detail(data)

    # ------------------------------------------------------------------
    # Normalization — adapt these two methods if your provider's JSON
    # shape differs. Everything else in the bot is provider-agnostic.
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_match_summary(raw: dict) -> MatchSummary:
        clubs = raw.get("clubs", {})
        club_ids = list(clubs.keys())
        if len(club_ids) != 2:
            raise ChelStatsError(f"Unexpected match summary shape, clubs={club_ids}")
        c1, c2 = club_ids
        return MatchSummary(
            match_id=str(raw["matchId"]),
            timestamp=int(raw["timestamp"]),
            club_id_home=int(c1),
            club_id_away=int(c2),
            score_home=int(clubs[c1].get("score", 0)),
            score_away=int(clubs[c2].get("score", 0)),
            raw=raw,
        )

    @staticmethod
    def _normalize_match_detail(raw: dict) -> MatchDetail:
        clubs = raw.get("clubs", {})
        club_ids = list(clubs.keys())
        if len(club_ids) != 2:
            raise ChelStatsError(f"Unexpected match detail shape, clubs={club_ids}")
        home_id, away_id = club_ids

        def team_box(cid: str) -> TeamBoxScore:
            c = clubs[cid]
            return TeamBoxScore(
                club_id=int(cid),
                goals=int(c.get("score", 0)),
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
                        gamertag=p["playername"],
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
                        is_win=bool(int(p.get("glwins", 0))),
                        is_ot_loss=bool(int(p.get("otlosses", 0))) if "otlosses" in p else False,
                    )
                )

        return MatchDetail(
            match_id=str(raw.get("matchId", "")),
            timestamp=int(raw.get("timestamp", 0)),
            went_to_overtime=bool(raw.get("wentToOt", False)),
            went_to_shootout=bool(raw.get("wentToShootout", False)),
            home=team_box(home_id),
            away=team_box(away_id),
            players=players,
            raw=raw,
        )

===== END OF FILE, COPY UP TO HERE =====
