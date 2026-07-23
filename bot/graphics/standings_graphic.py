"""Renders the full league standings table as a PNG, for #standings."""
from __future__ import annotations

import uuid
from typing import Sequence

from PIL import ImageDraw

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import StandingsEntry, Team

ROW_H = 58
HEADER_H = 130
LOGO_SIZE = 34
WIDTH = 1240

COL_X = {
    "rank": 40,
    "team": 110,
    "gp": 500,
    "w": 580,
    "l": 650,
    "otl": 720,
    "pts": 810,
    "gf": 890,
    "ga": 970,
    "diff": 1050,
    "streak": 1130,
}


async def render_standings(
    season_label: str,
    rows: Sequence[tuple[StandingsEntry, Team]],
    league_logo_url: str | None = None,
    background_url: str | None = None,
    accent_color: tuple[int, int, int] = Theme.ACCENT,
) -> str:
    height = HEADER_H + ROW_H * (len(rows) + 1) + 50
    img, draw = await prepare_canvas(WIDTH, height, accent_color, background_url, banner_height=HEADER_H)

    title_font = load_font("Black", 44)
    sub_font = load_font("Bold", 24)
    header_font = load_font("Bold", 18)
    row_font = load_font("Regular", 23)
    rank_font = load_font("Black", 24)

    draw.text((40, 28), "LEAGUE STANDINGS", font=title_font, fill=(255, 255, 255))
    draw.text((40, 82), season_label, font=sub_font, fill=(200, 210, 230))

    league_logo = await get_team_logo(league_logo_url, (80, 80))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 40 - 80, 25), league_logo.split()[-1])

    header_y = HEADER_H + 14
    for key, label in [
        ("team", "TEAM"),
        ("gp", "GP"),
        ("w", "W"),
        ("l", "L"),
        ("otl", "OTL"),
        ("pts", "PTS"),
        ("gf", "GF"),
        ("ga", "GA"),
        ("diff", "DIFF"),
        ("streak", "STRK"),
    ]:
        draw.text((COL_X[key], header_y), label, font=header_font, fill=Theme.TEXT_MUTED)
    draw.line([(40, HEADER_H + 44), (WIDTH - 40, HEADER_H + 44)], fill=accent_color, width=2)

    y = HEADER_H + 56
    for i, (entry, team) in enumerate(rows):
        team_color = Theme.team_color(team, fallback=accent_color)

        if i % 2 == 1:
            draw.rectangle([(0, y - 8), (WIDTH, y + ROW_H - 12)], fill=Theme.BG_PANEL)
        # Colored left accent bar per row, using the team's real color.
        draw.rectangle([(0, y - 8), (6, y + ROW_H - 12)], fill=team_color)

        rank_color = Theme.GOLD if entry.rank == 1 else (Theme.SILVER if entry.rank == 2 else (Theme.BRONZE if entry.rank == 3 else Theme.TEXT_PRIMARY))
        draw.text((COL_X["rank"], y), str(entry.rank), font=rank_font, fill=rank_color)

        logo = await get_team_logo(team.logo_url, (LOGO_SIZE, LOGO_SIZE))
        logo_x = COL_X["team"] - 44
        if logo is not None:
            img.paste(logo, (logo_x, y - 4), logo.split()[-1])
        else:
            draw.ellipse([(logo_x, y), (logo_x + LOGO_SIZE, y + LOGO_SIZE)], fill=team_color)
        draw.text((COL_X["team"], y + 4), team.name, font=row_font, fill=Theme.TEXT_PRIMARY)

        gp = entry.wins + entry.losses + entry.ot_losses
        diff_str = f"+{entry.goal_diff}" if entry.goal_diff > 0 else str(entry.goal_diff)
        diff_color = Theme.WIN_GREEN if entry.goal_diff > 0 else (Theme.LOSS_RED if entry.goal_diff < 0 else Theme.TEXT_SECONDARY)

        draw.text((COL_X["gp"], y + 4), str(gp), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["w"], y + 4), str(entry.wins), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["l"], y + 4), str(entry.losses), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["otl"], y + 4), str(entry.ot_losses), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["pts"], y + 4), str(entry.points), font=load_font("Black", 23), fill=(255, 255, 255))
        draw.text((COL_X["gf"], y + 4), str(entry.goals_for), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["ga"], y + 4), str(entry.goals_against), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["diff"], y + 4), diff_str, font=row_font, fill=diff_color)
        draw.text((COL_X["streak"], y + 4), entry.streak, font=row_font, fill=Theme.TEXT_SECONDARY)

        y += ROW_H

    out_path = GENERATED_DIR / f"standings_{uuid.uuid4().hex[:10]}.png"
    img.save(out_path)
    return str(out_path)
