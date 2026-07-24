"""Renders the league schedule as a graphic -- games grouped by week,
each showing its day/time slot, the matchup, and status."""
from __future__ import annotations

import uuid

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import ScheduleGame, Team
from bot.models.schedule import ScheduleStatus

WIDTH = 900
BANNER_H = 100
WEEK_HEADER_H = 36
ROW_H = 40
LOGO_SIZE = 24
MAX_GAMES_SHOWN = 60

STATUS_ICONS = {
    ScheduleStatus.SCHEDULED: ("🕒", Theme.TEXT_MUTED),
    ScheduleStatus.PLAYED: ("✅", Theme.WIN_GREEN),
    ScheduleStatus.FORFEITED: ("🚫", Theme.LOSS_RED),
    ScheduleStatus.POSTPONED: ("⏸️", Theme.GOLD),
    ScheduleStatus.CANCELLED: ("❌", Theme.LOSS_RED),
}


async def render_schedule(
    title: str,
    season_label: str,
    games: list[ScheduleGame],
    teams_by_id: dict[int, Team],
    league_logo_url: str | None = None,
    background_url: str | None = None,
    accent_color: tuple[int, int, int] = Theme.ACCENT,
) -> str:
    shown_games = games[:MAX_GAMES_SHOWN]
    truncated = len(games) > MAX_GAMES_SHOWN

    # Group by week, preserving order of first appearance.
    weeks: dict[object, list[ScheduleGame]] = {}
    for g in shown_games:
        weeks.setdefault(g.week, []).append(g)

    height = BANNER_H + len(weeks) * WEEK_HEADER_H + len(shown_games) * ROW_H + 50
    if truncated:
        height += 30

    img, draw = await prepare_canvas(WIDTH, height, accent_color, background_url, banner_height=BANNER_H)

    title_font = load_font("Black", 32)
    sub_font = load_font("Bold", 18)
    week_font = load_font("Black", 16)
    row_font = load_font("Regular", 16)
    time_font = load_font("Bold", 14)

    draw.text((32, 22), title, font=title_font, fill=(255, 255, 255))
    draw.text((34, 60), season_label, font=sub_font, fill=(210, 216, 230))

    league_logo = await get_team_logo(league_logo_url, (60, 60))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 32 - 60, 18), league_logo.split()[-1])

    y = BANNER_H + 10
    for week_num, week_games in weeks.items():
        week_label = f"WEEK {week_num}" if week_num is not None else "UNSCHEDULED"
        draw.text((32, y), week_label, font=week_font, fill=Theme.TEXT_MUTED)
        draw.line([(32, y + 24), (WIDTH - 32, y + 24)], fill=Theme.BORDER, width=1)
        y += WEEK_HEADER_H

        for g in week_games:
            home = teams_by_id.get(g.home_team_id)
            away = teams_by_id.get(g.away_team_id)
            icon, status_color = STATUS_ICONS.get(g.status, ("", Theme.TEXT_MUTED))

            slot_str = f"{(g.day_of_week or '')[:3]} {g.game_time or ''}".strip() or "—"
            draw.text((32, y + 4), slot_str, font=time_font, fill=Theme.TEXT_SECONDARY)

            x = 170
            home_logo = await get_team_logo(home.logo_url if home else None, (LOGO_SIZE, LOGO_SIZE))
            if home_logo is not None:
                img.paste(home_logo, (x, y), home_logo.split()[-1])
                x += LOGO_SIZE + 6
            home_name = home.name if home else "TBD"
            draw.text((x, y + 4), home_name, font=row_font, fill=Theme.TEXT_PRIMARY)

            vs_x = 480
            draw.text((vs_x, y + 4), "vs", font=row_font, fill=Theme.TEXT_MUTED)

            ax = vs_x + 36
            away_logo = await get_team_logo(away.logo_url if away else None, (LOGO_SIZE, LOGO_SIZE))
            if away_logo is not None:
                img.paste(away_logo, (ax, y), away_logo.split()[-1])
                ax += LOGO_SIZE + 6
            away_name = away.name if away else "TBD"
            draw.text((ax, y + 4), away_name, font=row_font, fill=Theme.TEXT_PRIMARY)

            game_number_str = f"#{g.game_number}"
            gn_w = draw.textlength(game_number_str, font=row_font)
            draw.text((WIDTH - 32 - 30 - gn_w, y + 4), game_number_str, font=row_font, fill=Theme.TEXT_MUTED)
            draw.text((WIDTH - 32 - 24, y + 2), icon, font=row_font, fill=status_color)

            y += ROW_H

    if truncated:
        draw.text((32, y + 6), f"+ {len(games) - MAX_GAMES_SHOWN} more games not shown -- use /league schedule week to see a specific week.", font=row_font, fill=Theme.TEXT_MUTED)

    out_path = GENERATED_DIR / f"schedule_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)
