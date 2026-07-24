"""Renders every stat category's leaderboard together in one image."""
from __future__ import annotations

import uuid

from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.services.leaders_service import LeaderRow

COLS = 3
CELL_W = 400
CELL_H = 230
ROWS_SHOWN = 5
PADDING = 40
BANNER_H = 90


async def render_combined_leaders_board(
    season_label: str,
    categories: list[tuple[str, list[LeaderRow]]],
    league_logo_url: str | None = None,
    background_url: str | None = None,
    accent_color: tuple[int, int, int] = Theme.ACCENT,
) -> str:
    num_rows = -(-len(categories) // COLS)
    width = PADDING * 2 + COLS * CELL_W
    height = PADDING * 2 + BANNER_H + num_rows * CELL_H

    img, draw = await prepare_canvas(width, height, accent_color, background_url, banner_height=BANNER_H + PADDING)

    title_font = load_font("Black", 36)
    sub_font = load_font("Bold", 20)
    cat_font = load_font("Bold", 20)
    row_font = load_font("Regular", 18)
    val_font = load_font("Black", 20)

    draw.text((PADDING, 20), "STAT LEADERS", font=title_font, fill=(255, 255, 255))
    draw.text((PADDING, 62), season_label, font=sub_font, fill=(210, 216, 230))

    grid_top = PADDING + BANNER_H

    for idx, (title, rows) in enumerate(categories):
        col = idx % COLS
        row = idx // COLS
        cell_x = PADDING + col * CELL_W
        cell_y = grid_top + row * CELL_H

        draw.rounded_rectangle(
            [(cell_x, cell_y), (cell_x + CELL_W - 20, cell_y + CELL_H - 16)],
            radius=10,
            fill=Theme.BG_PANEL,
            outline=accent_color,
            width=1,
        )
        draw.text((cell_x + 16, cell_y + 12), title.upper(), font=cat_font, fill=Theme.TEXT_MUTED)

        if not rows:
            draw.text((cell_x + 16, cell_y + 50), "No data yet", font=row_font, fill=Theme.TEXT_MUTED)
            continue

        line_y = cell_y + 48
        for r in rows[:ROWS_SHOWN]:
            name = r.player.gamertag
            max_name_width = CELL_W - 20 - 32 - 70
            display_name = _truncate_to_fit(draw, name, row_font, max_name_width)

            rank_color = Theme.GOLD if r.rank == 1 else (Theme.SILVER if r.rank == 2 else (Theme.BRONZE if r.rank == 3 else Theme.TEXT_MUTED))
            draw.text((cell_x + 16, line_y), str(r.rank), font=row_font, fill=rank_color)
            draw.text((cell_x + 40, line_y), display_name, font=row_font, fill=Theme.TEXT_PRIMARY)

            val_str = str(r.value) if isinstance(r.value, int) else f"{r.value:.3f}".lstrip("0") if r.value < 1 else f"{r.value:.2f}"
            val_w = draw.textlength(val_str, font=val_font)
            draw.text((cell_x + CELL_W - 30 - val_w, line_y - 1), val_str, font=val_font, fill=accent_color)

            line_y += 30

    out_path = GENERATED_DIR / f"combined_leaders_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)


def _truncate_to_fit(draw, text: str, font, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return (truncated + ellipsis) if truncated else ellipsis
