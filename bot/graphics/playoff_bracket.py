"""Renders a single-elimination playoff bracket -- rounds arranged left
to right, each series shown as a small card with both teams, the
series score, and real club logos where available.

Text-bleed fix: team names are now measured and truncated with an
ellipsis if they'd overflow the box width, instead of being drawn at
full length regardless of available space (which is what caused long
team names to run off the edge of the image in an earlier version)."""
from __future__ import annotations

import uuid

from PIL import Image, ImageDraw

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font
from bot.models import PlayoffSeries, Team

ROUND_WIDTH = 300
SERIES_HEIGHT = 100
SERIES_GAP = 24
LOGO_SIZE = 26
PADDING = 40
SCORE_RESERVED_WIDTH = 36  # space reserved on the right of each row for the win-count digit


async def render_playoff_bracket(
    season_label: str,
    rounds: list[list[PlayoffSeries]],
    teams_by_id: dict[int, Team],
    league_logo_url: str | None = None,
) -> str:
    if not rounds:
        raise ValueError("render_playoff_bracket called with no rounds")

    first_round_series_count = len(rounds[0])
    height = PADDING * 2 + 80 + first_round_series_count * (SERIES_HEIGHT + SERIES_GAP)
    width = PADDING * 2 + len(rounds) * ROUND_WIDTH

    img = Image.new("RGB", (width, height), Theme.BG_DARK)
    draw = ImageDraw.Draw(img)

    title_font = load_font("Black", 34)
    sub_font = load_font("Regular", 20)
    round_font = load_font("Bold", 16)
    team_font = load_font("Regular", 16)
    score_font = load_font("Black", 20)

    draw.text((PADDING, 20), "PLAYOFF BRACKET", font=title_font, fill=Theme.TEXT_PRIMARY)
    draw.text((PADDING, 58), season_label, font=sub_font, fill=Theme.TEXT_SECONDARY)

    league_logo = await get_team_logo(league_logo_url, (56, 56))
    if league_logo is not None:
        img.paste(league_logo, (width - PADDING - 56, 16), league_logo.split()[-1])

    top_y = PADDING + 80
    centers: list[list[float]] = []
    for round_index, series_list in enumerate(rounds):
        round_centers = []
        if round_index == 0:
            for i in range(len(series_list)):
                round_centers.append(top_y + i * (SERIES_HEIGHT + SERIES_GAP) + SERIES_HEIGHT / 2)
        else:
            prev_centers = centers[round_index - 1]
            for i in range(len(series_list)):
                c = (prev_centers[i * 2] + prev_centers[i * 2 + 1]) / 2
                round_centers.append(c)
        centers.append(round_centers)

    for round_index, series_list in enumerate(rounds):
        x = PADDING + round_index * ROUND_WIDTH
        draw.text((x, top_y - 28), series_list[0].round_name.upper(), font=round_font, fill=Theme.TEXT_MUTED)

        for i, series in enumerate(series_list):
            center_y = centers[round_index][i]
            box_y = center_y - SERIES_HEIGHT / 2
            box_w = ROUND_WIDTH - 40

            draw.rounded_rectangle(
                [(x, box_y), (x + box_w, box_y + SERIES_HEIGHT)], radius=8, fill=Theme.BG_PANEL, outline=Theme.BORDER, width=1
            )

            team_a = teams_by_id.get(series.team_a_id)
            team_b = teams_by_id.get(series.team_b_id)
            a_won = series.winner_team_id == series.team_a_id
            b_won = series.winner_team_id == series.team_b_id

            await _draw_team_row(draw, img, x, box_y + 8, box_w, team_a, series.seed_a, series.wins_a, a_won, team_font, score_font)
            draw.line([(x + 8, box_y + SERIES_HEIGHT / 2), (x + box_w - 8, box_y + SERIES_HEIGHT / 2)], fill=Theme.BORDER, width=1)
            await _draw_team_row(
                draw, img, x, box_y + SERIES_HEIGHT / 2 + 8, box_w, team_b, series.seed_b, series.wins_b, b_won, team_font, score_font
            )

            if round_index < len(rounds) - 1:
                next_center = centers[round_index + 1][i // 2]
                connector_x = x + box_w
                draw.line([(connector_x, center_y), (connector_x + 15, center_y)], fill=Theme.BORDER, width=2)
                draw.line([(connector_x + 15, center_y), (connector_x + 15, next_center)], fill=Theme.BORDER, width=2)
                draw.line([(connector_x + 15, next_center), (connector_x + 30, next_center)], fill=Theme.BORDER, width=2)

    out_path = GENERATED_DIR / f"bracket_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)


def _truncate_to_fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> str:
    """Shortens text with a trailing ellipsis until it fits max_width --
    this is the actual fix for team names bleeding off the edge of the
    bracket image. Falls back gracefully for very short max_width."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return (truncated + ellipsis) if truncated else ellipsis


async def _draw_team_row(draw, img, x, y, box_w, team, seed, wins, won, team_font, score_font) -> None:
    name_x = x + 10
    if team is not None:
        logo = await get_team_logo(team.logo_url, (LOGO_SIZE, LOGO_SIZE))
        if logo is not None:
            img.paste(logo, (int(name_x), int(y - 2)), logo.split()[-1])
            name_x += LOGO_SIZE + 6

    seed_str = f"({seed}) " if seed else ""
    raw_name = f"{seed_str}{team.name}" if team else "TBD"

    # Reserve space on the right for the score digit + a small margin, and
    # never let the name draw past that boundary -- this is what actually
    # stops long team names from bleeding off the image.
    available_width = (x + box_w) - name_x - SCORE_RESERVED_WIDTH - 10
    display_name = _truncate_to_fit(draw, raw_name, team_font, max(available_width, 20))

    color = Theme.WIN_GREEN if won else Theme.TEXT_PRIMARY
    draw.text((name_x, y), display_name, font=team_font, fill=color)

    score_str = str(wins)
    score_w = draw.textlength(score_str, font=score_font)
    draw.text((x + box_w - 16 - score_w, y - 2), score_str, font=score_font, fill=color)
