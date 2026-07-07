
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
"match detail" endpoint.

EA's server also checks the `Referer` header and blocks requests that
don't set it to an ea.com origin -- every request below sends that.

IMPORTANT CAVEATS -- read before assuming a failure is a bug in this code
--------------------------------------------------------------------------
1. EA's `club_private` match-history endpoint has been reported
   broken/unreliable by other developers across several NHL versions on
   EA's own forums -- independent of anything in this file.
2. EA's Pro Clubs API as a whole has had multi-week outages. If every
   request fails the same way regardless of Club ID, check EA's own
   forums for current outage reports before assuming this code is broken.
3. This is unversioned and undocumented -- EA can change the response
   shape at any time with no notice. `_normalize_match` below is the only
   method that should need editing if the JSON shape drifts from what's
   assumed here.
4. There's no documented "went to overtime" flag in the real payload.
   `_normalize_match` infers it from game length (time-on-ice exceeding
   60 regulation minutes) instead -- see the comment inside it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

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


def _split_proxy_credentials(proxy_url: str) -> tuple[Optional[str], Optional[aiohttp.BasicAuth]]:
    """aiohttp does not reliably pull username:password out of a proxy URL
    the way some other HTTP libraries (e.g. requests) do -- it needs the
    bare scheme://host:port passed as `proxy=` and the credentials passed
    separately as `proxy_auth=aiohttp.BasicAuth(...)`. Without this split,
    a proxy requiring auth can silently hang the connection waiting for
    credentials that never arrive, which looks identical to a network
    timeout -- this was the actual cause of continued timeouts even after
    a working proxy URL was configured."""
    if not proxy_url:
        return None, None
    parsed = urlsplit(proxy_url)
    if not parsed.username:
        return proxy_url, None
    bare = urlunsplit((parsed.scheme, f"{parsed.hostname}:{parsed.port}", parsed.path, parsed.query, parsed.fragment))
    auth = aiohttp.BasicAuth(login=parsed.username, password=parsed.password or "")
    return bare, auth


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
        proxy_url, proxy_auth = _split_proxy_credentials(settings.chelstats_proxy_url)
        async with aiohttp.ClientSession(headers=self._headers()) as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
                proxy=proxy_url,
                proxy_auth=proxy_auth,
            ) as resp:
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

    async def get_matches_by_id(self, club_id: int, match_ids: list[str]) -> list[MatchDetail]:
        """Fetch a club's recent matches and return only the ones whose
        match_id is in the given list -- used for combining a lagged-out
        game that split into multiple separate EA match records. Looks
        further back than the normal lookback window since the earlier
        half of a split game may have scrolled further down the list by
        the time someone notices the split and goes to combine it."""
        all_matches = await self.get_recent_club_matches(club_id, limit=max(settings.chelstats_match_lookback, 40))
        wanted = set(match_ids)
        return [m for m in all_matches if m.match_id in wanted]

    # ------------------------------------------------------------------
    # Normalization -- this is the one method to edit if EA's JSON shape
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

        # Real EA payload confirmed (July 2026): club-level score is under
        # "score", not "goals". There's no team-level hits/pim field, so we
        # sum those up from each club's players instead.
        def club_score(cid: str) -> int:
            return int(clubs[cid].get("score", 0))

        players: list[PlayerBoxScore] = []
        team_hits: dict[str, int] = {home_id: 0, away_id: 0}
        team_pim: dict[str, int] = {home_id: 0, away_id: 0}
        max_toi_seconds = 0

        for cid, roster in raw.get("players", {}).items():
            for player_id_key, p in roster.items():
                # Real payload has no "playerId" field inside the player
                # object -- the dict key itself IS the player's EA id.
                shots_against = int(p.get("glshots", 0) or 0)
                is_goalie = str(p.get("position", "")).lower() in ("goalie", "g") or shots_against > 0

                hits = int(p.get("skhits", 0) or 0)
                pim = int(p.get("skpim", 0) or 0)
                team_hits[cid] = team_hits.get(cid, 0) + hits
                team_pim[cid] = team_pim.get(cid, 0) + pim

                toi_seconds = int(p.get("toiseconds", 0) or 0)
                max_toi_seconds = max(max_toi_seconds, toi_seconds)

                # No explicit win/loss field for goalies in the real
                # payload -- derive it from the club's own score vs the
                # opponent's score for this match instead.
                is_win = club_score(cid) > club_score(away_id if cid == home_id else home_id)

                players.append(
                    PlayerBoxScore(
                        gamertag=p.get("playername", "Unknown"),
                        external_player_id=str(player_id_key),
                        club_id=int(cid),
                        is_goalie=is_goalie,
                        goals=int(p.get("skgoals", 0) or 0),
                        assists=int(p.get("skassists", 0) or 0),
                        plus_minus=int(p.get("skplusmin", 0) or 0),
                        hits=hits,
                        pim=pim,
                        shots=int(p.get("skshots", 0) or 0),
                        ppg=int(p.get("skppg", 0) or 0),
                        shots_against=shots_against,
                        saves=int(p.get("glsaves", 0) or 0),
                        goals_against=int(p.get("glga", 0) or 0),
                        minutes_played=toi_seconds / 60.0,
                        is_win=is_win if is_goalie else False,
                        is_ot_loss=False,  # filled in below, once we know match length
                    )
                )

        # No documented "went to overtime" flag exists in the real payload,
        # so we infer it from game length instead: regulation is 3x20-minute
        # periods = 3600 seconds. The player with the most time-on-ice
        # roughly tracks total game length (starters play close to the full
        # game), so if that exceeds regulation, the game went to OT/SO.
        # Small buffer (30s) avoids false positives from clock/stoppage
        # rounding right at the 60:00 mark. Shootout vs. plain overtime
        # can't be distinguished from this data (both just extend game
        # length), so any long game is tagged as overtime -- this still
        # correctly awards the OT loss point in standings either way; the
        # only cosmetic effect is the result graphic may say "(OT)" for
        # what was actually a shootout game.
        went_to_overtime = max_toi_seconds > (3600 + 30)

        if went_to_overtime:
            for player in players:
                if player.is_goalie and not player.is_win:
                    player.is_ot_loss = True

        def team_box(cid: str) -> TeamBoxScore:
            c = clubs[cid]
            return TeamBoxScore(
                club_id=int(cid),
                goals=club_score(cid),
                shots=int(c.get("shots", 0) or 0),
                hits=team_hits.get(cid, 0),
                pim=team_pim.get(cid, 0),
                powerplay_goals=int(c.get("ppg", 0) or 0),
                powerplay_opportunities=int(c.get("ppo", 0) or 0),
            )

        return MatchDetail(
            match_id=str(raw.get("matchId", raw.get("timestamp", ""))),
            timestamp=int(raw.get("timestamp", 0)),
            went_to_overtime=went_to_overtime,
            went_to_shootout=False,
            home=team_box(home_id),
            away=team_box(away_id),
            players=players,
            raw=raw,
        )


def combine_matches(matches: list[MatchDetail]) -> MatchDetail:
    """Merges multiple separate EA match records into one combined result
    -- for when a lagout/disconnect forces a league game to restart as a
    brand-new EASHL match instead of resuming the old one. Only ever
    called when a commissioner explicitly names the specific match IDs to
    combine (see `/entergame` with match_ids set); never auto-detected,
    since two clubs legitimately playing twice in one night looks
    identical to a lagout from the data alone.

    Team goals/shots/hits/pim and every player's stat line are SUMMED
    across all given matches. Time-on-ice sums too, so overtime detection
    (game length > regulation) still works correctly on the combined
    total. Uses the earliest match's timestamp as the combined game's
    played_at time.
    """
    if not matches:
        raise ChelStatsError("combine_matches called with no matches")
    if len(matches) == 1:
        return matches[0]

    ordered = sorted(matches, key=lambda m: m.timestamp)
    earliest = ordered[0]

    home_id, away_id = earliest.home.club_id, earliest.away.club_id

    def team_for(m: MatchDetail, cid: int) -> TeamBoxScore:
        return m.home if m.home.club_id == cid else m.away

    def sum_team(cid: int) -> TeamBoxScore:
        boxes = [team_for(m, cid) for m in ordered]
        return TeamBoxScore(
            club_id=cid,
            goals=sum(b.goals for b in boxes),
            shots=sum(b.shots for b in boxes),
            hits=sum(b.hits for b in boxes),
            pim=sum(b.pim for b in boxes),
            powerplay_goals=sum(b.powerplay_goals for b in boxes),
            powerplay_opportunities=sum(b.powerplay_opportunities for b in boxes),
        )

    combined_home = sum_team(home_id)
    combined_away = sum_team(away_id)

    # Sum each player's stat lines across all matches (a player who left
    # and reconnected shows up in each match's player list separately).
    merged_players: dict[str, PlayerBoxScore] = {}
    for m in ordered:
        for p in m.players:
            key = p.external_player_id or p.gamertag
            if key not in merged_players:
                merged_players[key] = PlayerBoxScore(
                    gamertag=p.gamertag,
                    external_player_id=p.external_player_id,
                    club_id=p.club_id,
                    is_goalie=p.is_goalie,
                )
            existing = merged_players[key]
            existing.goals += p.goals
            existing.assists += p.assists
            existing.plus_minus += p.plus_minus
            existing.hits += p.hits
            existing.pim += p.pim
            existing.shots += p.shots
            existing.ppg += p.ppg
            existing.shots_against += p.shots_against
            existing.saves += p.saves
            existing.goals_against += p.goals_against
            existing.minutes_played += p.minutes_played
            # Win/OT-loss reflect the FINAL match part's outcome, not each
            # individual part (the earlier parts were interrupted, not won
            # or lost in their own right).
            existing.is_win = p.is_win
            existing.is_ot_loss = p.is_ot_loss

    total_toi_seconds = max((p.minutes_played * 60 for p in merged_players.values()), default=0)
    went_to_overtime = total_toi_seconds > (3600 + 30)

    combined_raw = {"combined_from": [m.match_id for m in ordered], "parts": [m.raw for m in ordered]}

    return MatchDetail(
        match_id="+".join(sorted(m.match_id for m in ordered)),
        timestamp=earliest.timestamp,
        went_to_overtime=went_to_overtime,
        went_to_shootout=False,
        home=combined_home,
        away=combined_away,
        players=list(merged_players.values()),
        raw=combined_raw,
    )
