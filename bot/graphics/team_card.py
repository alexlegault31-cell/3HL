################################################################
FILE PATH TO TYPE ON GITHUB: bot/graphics/team_card.py
################################################################
"""Renders team profile cards (/team card) and weekly/leaders boards
(/leaders ...)."""
from __future__ import annotations

import uuid
from typing import Sequence

from PIL import Image, ImageDraw

from bot.graphics.theme import GENERATED_DIR, Theme, load_font
from bot.models import Team, TeamSeason
from bot.services.leaders_service import LeaderRow

WIDTH, HEIGHT = 760, 420


def render_team_card(team: Team, team_season: TeamSeason, season_label: str, leaders_lines: list[str]) -> str:
    img = Image.new("RGB", (WIDTH, HEIGHT), Theme.BG_DARK)
    draw = ImageDraw.Draw(img)

    accent = Theme.team_color(team)
    draw.rectangle([(0, 0), (WIDTH, 10)], fill=accent)
    draw.rounded_rectangle([(24, 30), (WIDTH - 24, HEIGHT - 24)], radius=18, fill=Theme.BG_PANEL, outline=Theme.BORDER, width=1)

    name_font = load_font("Black", 38)
    sub_font = load_font("Regular", 20)
    stat_label_font = load_font("Bold", 16)
    stat_val_font = load_font("Black", 34)
    leader_font = load_font("Regular", 18)

    draw.text((56, 58), team.name, font=name_font, fill=Theme.TEXT_PRIMARY)
    draw.text((58, 108), season_label, font=sub_font, fill=Theme.TEXT_SECONDARY)

    stats = [
        ("RECORD", f"{team_season.wins}-{team_season.losses}-{team_season.ot_losses}"),
        ("PTS", str(team_season.points)),
        ("GF", str(team_season.goals_for)),
        ("GA", str(team_season.goals_against)),
        ("DIFF", f"{'+' if team_season.goal_diff > 0 else ''}{team_season.goal_diff}"),
        ("STRK", f"{team_season.streak_type or '-'}{team_season.streak_count or ''}"),
    ]
    cols = 3
    cell_w = (WIDTH - 56 * 2) // cols
    start_y = 170
    for i, (label, value) in enumerate(stats):
        cx = 56 + (i % cols) * cell_w
        cy = start_y + (i // cols) * 90
        draw.text((cx, cy), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, cy + 22), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    draw.line([(56, 330), (WIDTH - 56, 330)], fill=Theme.BORDER, width=1)
    draw.text((56, 342), "TEAM LEADERS", font=stat_label_font, fill=Theme.TEXT_MUTED)
    y = 368
    for line in leaders_lines[:2]:
        draw.text((56, y), line, font=leader_font, fill=Theme.TEXT_SECONDARY)
        y += 24

    out_path = GENERATED_DIR / f"team_{team.id}_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)


def render_leaders_board(title: str, season_label: str, rows: Sequence[LeaderRow]) -> str:
    width = 760
    row_h = 54
    header_h = 120
    height = header_h + row_h * len(rows) + 30
    img = Image.new("RGB", (width, height), Theme.BG_DARK)
    draw = ImageDraw.Draw(img)

    title_font = load_font("Black", 34)
    sub_font = load_font("Regular", 20)
    row_font = load_font("Regular", 22)
    rank_font = load_font("Black", 24)
    val_font = load_font("Black", 26)
    sec_font = load_font("Regular", 16)

    draw.text((40, 24), title.upper(), font=title_font, fill=Theme.TEXT_PRIMARY)
    draw.text((40, 66), season_label, font=sub_font, fill=Theme.TEXT_SECONDARY)
    draw.line([(40, header_h - 6), (width - 40, header_h - 6)], fill=Theme.BORDER, width=2)

    y = header_h + 6
    for row in rows:
        if row.rank <= 3:
            medal_color = {1: Theme.GOLD, 2: Theme.SILVER, 3: Theme.BRONZE}[row.rank]
            draw.ellipse([(40, y + 6), (72, y + 38)], fill=medal_color)
            rw = draw.textlength(str(row.rank), font=rank_font)
            draw.text((40 + (32 - rw) / 2, y + 9), str(row.rank), font=rank_font, fill=(10, 10, 10))
        else:
            draw.text((48, y + 10), str(row.rank), font=rank_font, fill=Theme.TEXT_MUTED)

        name = row.player.gamertag
        team_suffix = f"  ·  {row.team.name}" if row.team else ""
        draw.text((96, y + 6), name, font=row_font, fill=Theme.TEXT_PRIMARY)
        name_w = draw.textlength(name, font=row_font)
        draw.text((96 + name_w, y + 9), team_suffix, font=sec_font, fill=Theme.TEXT_MUTED)

        val_str = str(row.value) if isinstance(row.value, int) else f"{row.value:.3f}".lstrip("0")
        val_w = draw.textlength(val_str, font=val_font)
        draw.text((width - 56 - val_w, y + 2), val_str, font=val_font, fill=Theme.ACCENT)
        if row.secondary:
            sec_w = draw.textlength(row.secondary, font=sec_font)
            draw.text((width - 56 - sec_w, y + 32), row.secondary, font=sec_font, fill=Theme.TEXT_MUTED)

        y += row_h

    out_path = GENERATED_DIR / f"leaders_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)

===== END OF FILE, COPY UP TO HERE =====
