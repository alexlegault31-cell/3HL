"""Renders the league schedule as a graphic -- weeks arranged in a 2-column
grid (week 1, then week 2 to its right, week 3 below week 1, and so on),
adaptively split across multiple images so a whole season is always shown
in full, never truncated, regardless of how many games it has."""
from __future__ import annotations

import uuid

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, finalize_and_save, load_font, prepare_canvas
from bot.models import ScheduleGame, Team
from bot.models.schedule import ScheduleStatus

COLS = 2
PAGE_WIDTH = 1600
PADDING = 32
COL_GAP = 40
COL_WIDTH = (PAGE_WIDTH - PADDING * 2 - COL_GAP * (COLS - 1)) // COLS

BANNER_H = 100
WEEK_HEADER_H = 36
ROW_H = 36
ROW_GAP_BETWEEN_WEEKS = 24
LOGO_SIZE = 20

# A page's height is capped so any single image stays a reasonable size to
# view/scroll -- once adding another row of weeks would exceed this, a new
# page (a separate image) starts instead. Dense schedules (many games per
# week) naturally get fewer weeks per page; sparse ones get more.
MAX_PAGE_HEIGHT = 2600

STATUS_ICONS = {
    ScheduleStatus.SCHEDULED: ("🕒", Theme.TEXT_MUTED),
    ScheduleStatus.PLAYED: ("✅", Theme.WIN_GREEN),
    ScheduleStatus.FORFEITED: ("🚫", Theme.LOSS_RED),
    ScheduleStatus.POSTPONED: ("⏸️", Theme.GOLD),
    ScheduleStatus.CANCELLED: ("❌", Theme.LOSS_RED),
}


def _row_height_for(week_rows: list[tuple]) -> int:
    max_games = max((len(games) for _, games in week_rows), default=0)
    return WEEK_HEADER_H + max_games * ROW_H + ROW_GAP_BETWEEN_WEEKS


def _paginate(week_items: list[tuple]) -> list[list[list[tuple]]]:
    """Groups (week_num, games) pairs into pages of grid ROWS -- each row
    is up to COLS weeks side by side. Starts a new page once the running
    height would exceed MAX_PAGE_HEIGHT, so dense schedules automatically
    get more (shorter) pages instead of one unreadably tall image."""
    rows = [week_items[i : i + COLS] for i in range(0, len(week_items), COLS)]

    pages: list[list[list[tuple]]] = []
    current_page: list[list[tuple]] = []
    current_height = BANNER_H + 40
    for row in rows:
        row_h = _row_height_for(row)
        if current_page and current_height + row_h > MAX_PAGE_HEIGHT:
            pages.append(current_page)
            current_page = []
            current_height = BANNER_H + 40
        current_page.append(row)
        current_height += row_h
    if current_page:
        pages.append(current_page)
    return pages


def _truncate_to_fit(draw, text: str, font, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return (truncated + ellipsis) if truncated else ellipsis


# Fixed column zones within COL_WIDTH, verified to never overlap regardless
# of team name length or game number size -- HOME and AWAY each get their
# own reserved budget, and the game#/icon block at the far right is
# reserved space that team names are truncated to never reach.
TIME_ZONE_END = 132  # measured against the actual widest realistic string, e.g. "Thu 12:00 PM EST" at ~122px
HOME_ZONE_END = 352
AWAY_ZONE_START = 362
AWAY_ZONE_END = 582
RIGHT_ZONE_START = 592  # game number + status icon


async def _draw_week_cell(img, draw, x: int, y: int, week_num, games: list[ScheduleGame], teams_by_id: dict[int, Team], fonts: dict) -> None:
    week_label = f"WEEK {week_num}" if week_num is not None else "UNSCHEDULED"
    draw.text((x, y), week_label, font=fonts["week"], fill=Theme.TEXT_MUTED)
    draw.line([(x, y + 24), (x + COL_WIDTH, y + 24)], fill=Theme.BORDER, width=1)

    row_y = y + WEEK_HEADER_H
    for g in games:
        home = teams_by_id.get(g.home_team_id)
        away = teams_by_id.get(g.away_team_id)
        icon, status_color = STATUS_ICONS.get(g.status, ("", Theme.TEXT_MUTED))

        slot_str = f"{(g.day_of_week or '')[:3]} {g.game_time or ''}".strip() or "—"
        draw.text((x, row_y + 2), slot_str, font=fonts["time"], fill=Theme.TEXT_SECONDARY)

        # HOME -- small green "H" tag makes home/away unambiguous without
        # relying on anyone knowing "left team = home" as a convention.
        home_x = x + TIME_ZONE_END
        draw.text((home_x, row_y + 2), "H", font=fonts["tag"], fill=Theme.WIN_GREEN)
        home_x += 14
        home_logo = await get_team_logo(home.logo_url if home else None, (LOGO_SIZE, LOGO_SIZE))
        if home_logo is not None:
            img.paste(home_logo, (home_x, row_y), home_logo.split()[-1])
            home_x += LOGO_SIZE + 5
        home_name_budget = (x + HOME_ZONE_END) - home_x - 4
        home_name = _truncate_to_fit(draw, home.name if home else "TBD", fonts["row"], home_name_budget)
        draw.text((home_x, row_y + 2), home_name, font=fonts["row"], fill=Theme.TEXT_PRIMARY)

        # AWAY -- same idea, muted-blue "A" tag for the visiting team.
        away_x = x + AWAY_ZONE_START
        draw.text((away_x, row_y + 2), "A", font=fonts["tag"], fill=Theme.ACCENT)
        away_x += 14
        away_logo = await get_team_logo(away.logo_url if away else None, (LOGO_SIZE, LOGO_SIZE))
        if away_logo is not None:
            img.paste(away_logo, (away_x, row_y), away_logo.split()[-1])
            away_x += LOGO_SIZE + 5
        away_name_budget = (x + AWAY_ZONE_END) - away_x - 4
        away_name = _truncate_to_fit(draw, away.name if away else "TBD", fonts["row"], away_name_budget)
        draw.text((away_x, row_y + 2), away_name, font=fonts["row"], fill=Theme.TEXT_PRIMARY)

        # Game number + status icon computed FIRST (before the code), so
        # the code's available width can be measured against wherever the
        # game number actually starts this row -- varies with digit count.
        game_number_str = f"#{g.game_number}"
        gn_w = draw.textlength(game_number_str, font=fonts["row"])
        game_number_x = x + COL_WIDTH - 30 - gn_w

        if home and home.game_code:
            code_zone_start = x + AWAY_ZONE_END + 10
            code_zone_end = game_number_x - 10
            code_str = _truncate_to_fit(draw, home.game_code, fonts["time"], max(0, code_zone_end - code_zone_start))
            draw.text((code_zone_start, row_y + 4), code_str, font=fonts["time"], fill=Theme.ACCENT)

        draw.text((game_number_x, row_y + 2), game_number_str, font=fonts["row"], fill=Theme.TEXT_MUTED)
        draw.text((x + COL_WIDTH - 20, row_y), icon, font=fonts["row"], fill=status_color)

        row_y += ROW_H


async def render_schedule(
    title: str,
    season_label: str,
    games: list[ScheduleGame],
    teams_by_id: dict[int, Team],
    league_logo_url: str | None = None,
    background_url: str | None = None,
    accent_color: tuple[int, int, int] = Theme.ACCENT,
) -> list[str]:
    """Returns a LIST of image file paths -- one per page -- so the whole
    schedule is always shown in full, never truncated. Callers should
    attach every returned path."""
    weeks: dict[object, list[ScheduleGame]] = {}
    for g in games:
        weeks.setdefault(g.week, []).append(g)
    week_items = list(weeks.items())

    pages = _paginate(week_items)

    fonts = {
        "title": load_font("Black", 30),
        "sub": load_font("Bold", 17),
        "week": load_font("Black", 15),
        "row": load_font("Regular", 14),
        "time": load_font("Bold", 12),
        "tag": load_font("Black", 12),
    }

    out_paths = []
    for page_idx, page_rows in enumerate(pages):
        page_height = BANNER_H + sum(_row_height_for(r) for r in page_rows) + 40
        img, draw = await prepare_canvas(PAGE_WIDTH, page_height, accent_color, background_url, banner_height=BANNER_H)

        page_title = title if len(pages) == 1 else f"{title} — Page {page_idx + 1}/{len(pages)}"
        draw.text((32, 22), page_title, font=fonts["title"], fill=(255, 255, 255))
        draw.text((34, 58), season_label, font=fonts["sub"], fill=(210, 216, 230))

        league_logo = await get_team_logo(league_logo_url, (60, 60))
        if league_logo is not None:
            img.paste(league_logo, (PAGE_WIDTH - 32 - 60, 18), league_logo.split()[-1])

        y = BANNER_H + 20
        for row in page_rows:
            row_h = _row_height_for(row)
            for col_idx, (week_num, week_games) in enumerate(row):
                cell_x = PADDING + col_idx * (COL_WIDTH + COL_GAP)
                await _draw_week_cell(img, draw, cell_x, y, week_num, week_games, teams_by_id, fonts)
            y += row_h

        out_path = GENERATED_DIR / f"schedule_{uuid.uuid4().hex[:8]}.png"
        finalize_and_save(img, out_path)
        out_paths.append(str(out_path))

    return out_paths
