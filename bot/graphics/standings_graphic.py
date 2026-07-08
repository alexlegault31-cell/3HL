"""Renders the full league standings table as a PNG, for #standings."""
from __future__ import annotations

import uuid
from typing import Sequence

from PIL import Image, ImageDraw

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font
from bot.models import StandingsEntry, Team

ROW_H = 56
HEADER_H = 110
LOGO_SIZE = 32
COL_X = {
    "rank": 40,
    "team": 100,
    "gp": 480,
    "w": 560,
    "l": 630,
    "otl": 700,
    "pts": 790,
    "gf": 870,
    "ga": 950,
    "diff": 1030,
    "streak": 1110,
}
WIDTH = 1240


async def render_standings(
    season_label: str,
    rows: Sequence[tuple[StandingsEntry, Team]],
    league_logo_url: str | None = None,
) -> str:
    height = HEADER_H + ROW_H * (len(rows) + 1) + 40
    img = Image.new("RGB", (WIDTH, height), Theme.BG_DARK)
    draw = ImageDraw.Draw(img)

    title_font = load_font("Black", 40)
    sub_font = load_font("Regular", 22)
    header_font = load_font("Bold", 18)
    row_font = load_font("Regular", 22)
    rank_font = load_font("Bold", 22)

    draw.text((40, 24), "LEAGUE STANDINGS", font=title_font, fill=Theme.TEXT_PRIMARY)
    draw.text((40, 70), season_label, font=sub_font, fill=Theme.TEXT_SECONDARY)

    league_logo = await get_team_logo(league_logo_url, (64, 64))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 40 - 64, 24), league_logo.split()[-1])

    header_y = HEADER_H - 4
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
    draw.line([(40, HEADER_H + 22), (WIDTH - 40, HEADER_H + 22)], fill=Theme.BORDER, width=2)

    y = HEADER_H + 32
    for i, (entry, team) in enumerate(rows):
        if i % 2 == 1:
            draw.rectangle([(0, y - 6), (WIDTH, y + ROW_H - 10)], fill=Theme.BG_PANEL)

        rank_color = Theme.GOLD if entry.rank == 1 else Theme.TEXT_PRIMARY
        draw.text((COL_X["rank"], y), str(entry.rank), font=rank_font, fill=rank_color)

        logo = await get_team_logo(team.logo_url, (LOGO_SIZE, LOGO_SIZE))
        logo_x, logo_y = COL_X["team"] - 40, y + (ROW_H - LOGO_SIZE) // 2 - 14
        if logo is not None:
            img.paste(logo, (logo_x, logo_y), logo.split()[-1])
        else:
            color_dot = Theme.team_color(team)
            draw.ellipse([(COL_X["team"] - 28, y + 4), (COL_X["team"] - 8, y + 24)], fill=color_dot)
        draw.text((COL_X["team"], y), team.name, font=row_font, fill=Theme.TEXT_PRIMARY)

        gp = entry.wins + entry.losses + entry.ot_losses
        diff_str = f"+{entry.goal_diff}" if entry.goal_diff > 0 else str(entry.goal_diff)
        diff_color = Theme.WIN_GREEN if entry.goal_diff > 0 else (Theme.LOSS_RED if entry.goal_diff < 0 else Theme.TEXT_SECONDARY)

        draw.text((COL_X["gp"], y), str(gp), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["w"], y), str(entry.wins), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["l"], y), str(entry.losses), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["otl"], y), str(entry.ot_losses), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["pts"], y), str(entry.points), font=load_font("Bold", 22), fill=Theme.TEXT_PRIMARY)
        draw.text((COL_X["gf"], y), str(entry.goals_for), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["ga"], y), str(entry.goals_against), font=row_font, fill=Theme.TEXT_SECONDARY)
        draw.text((COL_X["diff"], y), diff_str, font=row_font, fill=diff_color)
        draw.text((COL_X["streak"], y), entry.streak, font=row_font, fill=Theme.TEXT_SECONDARY)

        y += ROW_H

    out_path = GENERATED_DIR / f"standings_{uuid.uuid4().hex[:10]}.png"
    img.save(out_path)
    return str(out_path)
