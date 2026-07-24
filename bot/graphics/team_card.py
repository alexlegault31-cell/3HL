"""Renders the club stats card for /league club stats -- logo/name
header, win-loss-points summary, last-10 form strip, full roster split
by skater/goalie, and match history. This is the one card that keeps
its team logo, by explicit request -- every other graphic in the bot
has logos removed.

Also renders the stat leaders board (used by /leaders and the combined
stat-leaders refresh), unchanged from before."""
from __future__ import annotations

import uuid
from typing import Sequence

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Team, TeamSeason
from bot.services.leaders_service import LeaderRow

WIDTH = 900
BANNER_H = 110
STAT_ROW_H = 90
FORM_ROW_H = 125
MEMBERS_HEADER_H = 40
ROSTER_ROW_H = 26
HISTORY_ROW_H = 26
LOGO_SIZE = 72

RESULT_COLORS = {"W": Theme.WIN_GREEN, "T": Theme.GOLD, "L": Theme.LOSS_RED, "O": (74, 144, 226)}
RESULT_LABELS = {"W": "W", "T": "OTW", "L": "L", "O": "OTL"}
ROW_LOGO_SIZE = 28


async def render_team_card(
    team: Team,
    team_season: TeamSeason,
    season_label: str,
    leaders_lines: list[str] | None = None,  # kept for call-site compatibility, unused in this layout
    league_logo_url: str | None = None,
    background_url: str | None = None,
    recent_results: list | None = None,
    skaters: list | None = None,
    goalies: list | None = None,
) -> str:
    recent_results = recent_results or []
    skaters = skaters or []
    goalies = goalies or []

    members_h = MEMBERS_HEADER_H + 24
    if skaters:
        members_h += 24 + len(skaters) * ROSTER_ROW_H
    if goalies:
        members_h += 24 + len(goalies) * ROSTER_ROW_H
    if not skaters and not goalies:
        members_h += 24

    history_h = 40 + max(len(recent_results), 1) * HISTORY_ROW_H

    height = BANNER_H + STAT_ROW_H + FORM_ROW_H + members_h + history_h + 40

    accent = Theme.team_color(team)
    img, draw = await prepare_canvas(WIDTH, height, accent, background_url, banner_height=BANNER_H)

    name_font = load_font("Black", 36)
    sub_font = load_font("Regular", 19)
    section_font = load_font("Black", 18)
    stat_label_font = load_font("Bold", 15)
    stat_val_font = load_font("Black", 30)
    form_font = load_font("Bold", 13)
    row_header_font = load_font("Bold", 13)
    row_font = load_font("Regular", 15)
    record_font = load_font("Regular", 15)

    # --- Header: logo + name + league/season line ---
    logo = await get_team_logo(team.logo_url, (LOGO_SIZE, LOGO_SIZE))
    name_x = 32
    if logo is not None:
        img.paste(logo, (32, 18), logo.split()[-1])
        name_x = 32 + LOGO_SIZE + 16
    draw.text((name_x, 20), team.name, font=name_font, fill=(255, 255, 255))
    draw.text((name_x + 2, 66), season_label, font=sub_font, fill=(210, 216, 230))

    # --- Win/OTW/Loss/OTL/Points row ---
    stat_top = BANNER_H + 16
    ot_wins = getattr(team_season, "ot_wins", 0)
    stats = [
        ("WINS", str(team_season.wins)),
        ("OT WINS", str(ot_wins)),
        ("LOSSES", str(team_season.losses)),
        ("OTL", str(team_season.ot_losses)),
        ("POINTS", str(team_season.points)),
    ]
    cell_w = (WIDTH - 64) // len(stats)
    for i, (label, value) in enumerate(stats):
        cx = 32 + i * cell_w
        draw.text((cx, stat_top), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, stat_top + 24), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    # --- Last 10 form strip + streak + record ---
    form_top = BANNER_H + STAT_ROW_H
    draw.line([(32, form_top), (WIDTH - 32, form_top)], fill=accent, width=2)
    draw.text((32, form_top + 12), "LAST 10 GAMES", font=section_font, fill=Theme.TEXT_PRIMARY)

    last_10 = (team_season.last_10 or "")[-10:]
    box_x = 32
    box_y = form_top + 42
    box_size = 28
    for code in last_10:
        color = RESULT_COLORS.get(code, Theme.BORDER)
        draw.rounded_rectangle([(box_x, box_y), (box_x + box_size, box_y + box_size)], radius=5, fill=color)
        label = RESULT_LABELS.get(code, "?")
        lw = draw.textlength(label, font=form_font)
        draw.text((box_x + (box_size - lw) / 2, box_y + 7), label, font=form_font, fill=(10, 10, 10))
        box_x += box_size + 6

    streak_str = f"{team_season.streak_type or '-'}{team_season.streak_count or ''}"
    record_str = f"{team_season.wins}-{ot_wins}-{team_season.losses}-{team_season.ot_losses} (W-OTW-L-OTL)"
    draw.text((32, box_y + 40), f"Streak: {streak_str}   •   Record: {record_str}", font=record_font, fill=Theme.TEXT_SECONDARY)

    # --- Members ---
    members_top = form_top + FORM_ROW_H
    draw.line([(32, members_top), (WIDTH - 32, members_top)], fill=accent, width=2)
    draw.text((32, members_top + 12), "MEMBERS", font=section_font, fill=Theme.TEXT_PRIMARY)

    y = members_top + 44
    if not skaters and not goalies:
        draw.text((32, y), "No games played yet this season.", font=row_font, fill=Theme.TEXT_MUTED)
        y += 24

    sk_cols = {"name": 32, "gp": 340, "g": 420, "a": 490, "p": 560, "ppg": 630}
    if skaters:
        draw.text((sk_cols["name"], y), "SKATERS", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((sk_cols["gp"], y), "GP", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((sk_cols["g"], y), "G", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((sk_cols["a"], y), "A", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((sk_cols["p"], y), "P", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((sk_cols["ppg"], y), "PPG", font=row_header_font, fill=Theme.TEXT_MUTED)
        y += 22
        for i, s in enumerate(skaters):
            if i % 2 == 1:
                draw.rectangle([(24, y - 3), (WIDTH - 24, y + ROSTER_ROW_H - 6)], fill=Theme.BG_PANEL)
            draw.text((sk_cols["name"], y), s.gamertag, font=row_font, fill=Theme.TEXT_PRIMARY)
            draw.text((sk_cols["gp"], y), str(s.games_played), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((sk_cols["g"], y), str(s.goals), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((sk_cols["a"], y), str(s.assists), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((sk_cols["p"], y), str(s.points), font=row_font, fill=Theme.TEXT_PRIMARY)
            draw.text((sk_cols["ppg"], y), str(s.ppg), font=row_font, fill=Theme.TEXT_SECONDARY)
            y += ROSTER_ROW_H

    gl_cols = {"name": 32, "gp": 340, "ga": 420, "gaa": 480, "saves": 550, "svpct": 630, "so": 710}
    if goalies:
        y += 8
        draw.text((gl_cols["name"], y), "GOALIES", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((gl_cols["gp"], y), "GP", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((gl_cols["ga"], y), "GA", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((gl_cols["gaa"], y), "GAA", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((gl_cols["saves"], y), "SAVES", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((gl_cols["svpct"], y), "SV%", font=row_header_font, fill=Theme.TEXT_MUTED)
        draw.text((gl_cols["so"], y), "SO", font=row_header_font, fill=Theme.TEXT_MUTED)
        y += 22
        for i, g in enumerate(goalies):
            if i % 2 == 1:
                draw.rectangle([(24, y - 3), (WIDTH - 24, y + ROSTER_ROW_H - 6)], fill=Theme.BG_PANEL)
            draw.text((gl_cols["name"], y), g.gamertag, font=row_font, fill=Theme.TEXT_PRIMARY)
            draw.text((gl_cols["gp"], y), str(g.games_played), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((gl_cols["ga"], y), str(g.goals_against), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((gl_cols["gaa"], y), f"{g.gaa:.2f}", font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((gl_cols["saves"], y), str(g.saves), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((gl_cols["svpct"], y), f"{g.save_pct:.3f}".lstrip("0"), font=row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((gl_cols["so"], y), str(g.shutouts), font=row_font, fill=Theme.TEXT_SECONDARY)
            y += ROSTER_ROW_H

    # --- Match History ---
    history_top = y + 16
    draw.line([(32, history_top), (WIDTH - 32, history_top)], fill=accent, width=2)
    draw.text((32, history_top + 12), "MATCH HISTORY", font=section_font, fill=Theme.TEXT_PRIMARY)

    hy = history_top + 44
    if not recent_results:
        draw.text((32, hy), "No games played yet this season.", font=row_font, fill=Theme.TEXT_MUTED)
    else:
        for r in recent_results:
            win_color = Theme.WIN_GREEN if r.is_win else Theme.LOSS_RED
            suffix = " (OT)" if r.is_ot else (" (forfeit)" if r.is_forfeit else "")
            if r.is_home:
                line = f"{team.name} {r.goals_for} - {r.goals_against} {r.opponent.name}{suffix}"
            else:
                line = f"{r.opponent.name} {r.goals_against} - {r.goals_for} {team.name}{suffix}"
            draw.text((32, hy), line, font=row_font, fill=win_color)
            hy += HISTORY_ROW_H

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
