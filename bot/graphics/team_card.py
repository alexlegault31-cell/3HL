"""Renders team profile cards (/league club stats) and stat leader boards
(/leaders ...), with real club crests and a gradient banner (or custom
background photo) instead of a flat dark card."""
from __future__ import annotations

import uuid
from typing import Sequence

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Team, TeamSeason
from bot.services.leaders_service import LeaderRow

WIDTH, HEIGHT = 780, 440
CARD_LOGO_SIZE = 72
ROW_LOGO_SIZE = 30
BANNER_H = 110


async def render_team_card(
    team: Team,
    team_season: TeamSeason,
    season_label: str,
    leaders_lines: list[str],
    league_logo_url: str | None = None,
    background_url: str | None = None,
) -> str:
    accent = Theme.team_color(team)
    img, draw = await prepare_canvas(WIDTH, HEIGHT, accent, background_url, banner_height=BANNER_H)

    name_font = load_font("Black", 38)
    sub_font = load_font("Regular", 20)
    stat_label_font = load_font("Bold", 16)
    stat_val_font = load_font("Black", 34)
    leader_font = load_font("Regular", 18)

    draw.text((32, 24), team.name, font=name_font, fill=(255, 255, 255))
    draw.text((34, 74), season_label, font=sub_font, fill=(210, 216, 230))

    logo = await get_team_logo(team.logo_url, (CARD_LOGO_SIZE, CARD_LOGO_SIZE))
    if logo is not None:
        img.paste(logo, (WIDTH - 32 - CARD_LOGO_SIZE, 20), logo.split()[-1])

    league_logo = await get_team_logo(league_logo_url, (44, 44))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 32 - CARD_LOGO_SIZE - 56, 33), league_logo.split()[-1])

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
    start_y = BANNER_H + 40
    for i, (label, value) in enumerate(stats):
        cx = 56 + (i % cols) * cell_w
        cy = start_y + (i // cols) * 90
        draw.text((cx, cy), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, cy + 22), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    line_y = start_y + 200
    draw.line([(56, line_y), (WIDTH - 56, line_y)], fill=accent, width=2)
    draw.text((56, line_y + 12), "TEAM LEADERS", font=stat_label_font, fill=Theme.TEXT_MUTED)
    y = line_y + 38
    for line in leaders_lines[:2]:
        draw.text((56, y), line, font=leader_font, fill=Theme.TEXT_SECONDARY)
        y += 24

    out_path = GENERATED_DIR / f"team_{team.id}_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)


async def render_leaders_board(
    title: str,
    season_label: str,
    rows: Sequence[LeaderRow],
    league_logo_url: str | None = None,
    background_url: str | None = None,
    accent_color: tuple[int, int, int] = Theme.ACCENT,
) -> str:
    width = 780
    row_h = 56
    header_h = 120
    height = header_h + row_h * max(len(rows), 1) + 30

    img, draw = await prepare_canvas(width, height, accent_color, background_url, banner_height=header_h)

    title_font = load_font("Black", 34)
    sub_font = load_font("Bold", 20)
    row_font = load_font("Regular", 22)
    rank_font = load_font("Black", 24)
    val_font = load_font("Black", 26)
    sec_font = load_font("Regular", 16)

    draw.text((40, 24), title.upper(), font=title_font, fill=(255, 255, 255))
    draw.text((40, 66), season_label, font=sub_font, fill=(210, 216, 230))

    league_logo = await get_team_logo(league_logo_url, (60, 60))
    if league_logo is not None:
        img.paste(league_logo, (width - 40 - 60, 18), league_logo.split()[-1])

    draw.line([(40, header_h - 6), (width - 40, header_h - 6)], fill=accent_color, width=2)

    if not rows:
        draw.text((40, header_h + 20), "No data recorded yet this season.", font=row_font, fill=Theme.TEXT_MUTED)
        out_path = GENERATED_DIR / f"leaders_{uuid.uuid4().hex[:8]}.png"
        img.save(out_path)
        return str(out_path)

    y = header_h + 6
    for row in rows:
        if row.rank <= 3:
            medal_color = {1: Theme.GOLD, 2: Theme.SILVER, 3: Theme.BRONZE}[row.rank]
            draw.ellipse([(40, y + 6), (72, y + 38)], fill=medal_color)
            rw = draw.textlength(str(row.rank), font=rank_font)
            draw.text((40 + (32 - rw) / 2, y + 9), str(row.rank), font=rank_font, fill=(10, 10, 10))
        else:
            draw.text((48, y + 10), str(row.rank), font=rank_font, fill=Theme.TEXT_MUTED)

        name_x = 96
        if row.team is not None:
            logo = await get_team_logo(row.team.logo_url, (ROW_LOGO_SIZE, ROW_LOGO_SIZE))
            if logo is not None:
                img.paste(logo, (name_x, y + 11), logo.split()[-1])
                name_x += ROW_LOGO_SIZE + 10

        name = row.player.gamertag
        team_suffix = f"  ·  {row.team.name}" if row.team else ""
        draw.text((name_x, y + 6), name, font=row_font, fill=Theme.TEXT_PRIMARY)
        name_w = draw.textlength(name, font=row_font)
        draw.text((name_x + name_w, y + 9), team_suffix, font=sec_font, fill=Theme.TEXT_MUTED)

        val_str = str(row.value) if isinstance(row.value, int) else f"{row.value:.3f}".lstrip("0")
        val_w = draw.textlength(val_str, font=val_font)
        draw.text((width - 56 - val_w, y + 2), val_str, font=val_font, fill=accent_color)
        if row.secondary:
            sec_w = draw.textlength(row.secondary, font=sec_font)
            draw.text((width - 56 - sec_w, y + 32), row.secondary, font=sec_font, fill=Theme.TEXT_MUTED)

        y += row_h

    out_path = GENERATED_DIR / f"leaders_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)
