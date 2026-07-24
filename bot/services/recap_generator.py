"""
Generates the short AI recap posted to #game-results after every import,
e.g.:

    Italy defeats France 5-2.
    Toaster x 72 scored twice and added an assist.
    Italy improves to 7-2-0 and remains first in the standings.

Falls back to a deterministic template (no API call) if RECAPS_ENABLED is
false or no OPENAI_API_KEY is configured, so the bot never breaks an
import just because the AI step is unavailable.

Cycles through several different tones/styles each call (both for the AI
path and the fallback templates) so consecutive recaps don't all read
identically, even for similar score lines.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from openai import AsyncOpenAI

from bot.config import settings
from bot.models import Game, GoalieGameStat, Player, PlayerGameStat, Team, TeamSeason

log = logging.getLogger(__name__)


@dataclass
class RecapContext:
    game: Game
    home_team: Team
    away_team: Team
    home_team_season: TeamSeason
    away_team_season: TeamSeason
    standings_rank_home: int
    standings_rank_away: int
    top_performers: list[str]  # pre-formatted "Name G+A" strings, best first


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _winner_loser(ctx: RecapContext) -> tuple[Team, Team, int, int]:
    if ctx.game.home_score >= ctx.game.away_score:
        return ctx.home_team, ctx.away_team, ctx.game.home_score, ctx.game.away_score
    return ctx.away_team, ctx.home_team, ctx.game.away_score, ctx.game.home_score


# Each AI recap picks one of these tone/style instructions at random, so
# the model's actual writing style varies call-to-call instead of always
# reading like the same beat reporter wrote every recap.
STYLE_VARIANTS = [
    "Tone: energetic beat-reporter, punchy short sentences, no purple prose.",
    "Tone: dry, understated, stats-first -- like a box-score ticker with a pulse.",
    "Tone: dramatic sports commentator building up the moment, but still factual.",
    "Tone: casual rec-league buddy texting a friend who missed the game.",
    "Tone: old-school newspaper sports column, a little formal, clipped sentences.",
    "Tone: hype hockey-Twitter style, excitable but still just reporting facts.",
]

# The deterministic fallback (used when the AI path is disabled/unavailable)
# also cycles through a few different phrasings so it isn't always the
# exact same sentence shape every single time.
FALLBACK_TEMPLATES = [
    "{winner} defeats {loser} {wscore}-{lscore}.",
    "{winner} takes down {loser}, {wscore}-{lscore}.",
    "Final: {winner} {wscore}, {loser} {lscore}.",
    "{winner} comes out on top against {loser}, {wscore}-{lscore}.",
]


def _fallback_recap(ctx: RecapContext) -> str:
    winner, loser, wscore, lscore = _winner_loser(ctx)
    winner_ts = ctx.home_team_season if winner.id == ctx.home_team.id else ctx.away_team_season
    record = f"{winner_ts.wins}-{winner_ts.losses}-{winner_ts.ot_losses}"
    rank = ctx.standings_rank_home if winner.id == ctx.home_team.id else ctx.standings_rank_away

    headline = random.choice(FALLBACK_TEMPLATES).format(winner=winner.name, loser=loser.name, wscore=wscore, lscore=lscore)
    lines = [headline]
    if ctx.top_performers:
        lines.append(ctx.top_performers[0])
    lines.append(f"{winner.name} improves to {record} and sits #{rank} in the standings.")
    return "\n".join(lines)


async def generate_recap(ctx: RecapContext) -> str:
    if not settings.recaps_enabled or not settings.openai_api_key:
        return _fallback_recap(ctx)

    winner, loser, wscore, lscore = _winner_loser(ctx)
    winner_ts = ctx.home_team_season if winner.id == ctx.home_team.id else ctx.away_team_season
    record = f"{winner_ts.wins}-{winner_ts.losses}-{winner_ts.ot_losses}"
    rank = ctx.standings_rank_home if winner.id == ctx.home_team.id else ctx.standings_rank_away

    style = random.choice(STYLE_VARIANTS)
    prompt = (
        "Write a tight 3-4 sentence hockey game recap for a fan Discord channel. "
        f"{style} No emojis, no hashtags. "
        f"{winner.name} beat {loser.name} {wscore}-{lscore}"
        f"{' in overtime' if ctx.game.went_to_overtime else ''}"
        f"{' in a shootout' if ctx.game.went_to_shootout else ''}. "
        f"{winner.name} is now {record} and ranked #{rank} in the standings. "
        "Top performers: " + "; ".join(ctx.top_performers[:3]) + ". "
        "Mention the standout performer by name and weave the team's updated record/rank into "
        "the final sentence. Do not invent stats not given above."
    )

    try:
        client = _get_client()
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are a concise hockey beat reporter for an online amateur league. Vary your sentence structure and opening line each time -- never start two recaps the same way."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
            temperature=1.0,
        )
        text = resp.choices[0].message.content
        return text.strip() if text else _fallback_recap(ctx)
    except Exception:  # noqa: BLE001
        log.exception("Recap generation failed, falling back to template")
        return _fallback_recap(ctx)


def format_top_performers(player_lines: list[tuple[Player, PlayerGameStat]], goalie_lines: list[tuple[Player, GoalieGameStat]]) -> list[str]:
    """Builds 'Name G+A' style strings, skaters sorted by points then goalie
    shutouts/wins surfaced, for feeding into the recap prompt and as the
    fallback template's headline stat."""
    out: list[str] = []
    skaters = sorted(player_lines, key=lambda pl: (pl[1].points, pl[1].goals), reverse=True)
    for player, line in skaters[:3]:
        bits = []
        if line.goals:
            bits.append(f"scored {line.goals}" if line.goals == 1 else f"scored {line.goals} goals")
        if line.assists:
            bits.append(f"added {line.assists} assist" + ("s" if line.assists > 1 else ""))
        if bits:
            out.append(f"{player.gamertag} " + " and ".join(bits) + ".")
    for player, gline in goalie_lines:
        if gline.shutout:
            out.append(f"{player.gamertag} posted a shutout, stopping all {gline.shots_against} shots.")
        elif gline.result == 1:
            out.append(f"{player.gamertag} earned the win with {gline.saves} saves on {gline.shots_against} shots.")
    return out
