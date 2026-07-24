"""Renders the final-score graphic posted to #game-results after every
/entergame import or recorded forfeit."""
from __future__ import annotations

import uuid

from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Game, Team

WIDTH, HEIGHT = 1000, 460


async def render_game_result(
    game: Game,
    home_team: Team,
    away_team: Team,
    league_logo_url: str | None = None,
    background_url: str | None = None,
) -> str:
    home_color = Theme.team_color(home_team, fallback=Theme.ACCENT)
    away_color = Theme.team_color(away_team, fallback=Theme.LOSS_RED)

    img, draw = await prepare_canvas(WIDTH, HEIGHT, home_color, background_url, banner_height=None)

    # Side panels with each team's color, fading toward center -- always
    # drawn even over a custom background, so the two teams stay visually
    # anchored to their brand colors.
    draw.rectangle([(0, 0), (WIDTH // 2, 14)], fill=home_color)
    draw.rectangle([(WIDTH // 2, 0), (WIDTH, 14)], fill=away_color)

    label_font = load_font("Bold", 26)
    name_font = load_font("Black", 46)
    score_font = load_font("Black", 110)
    meta_font = load_font("Regular", 24)
    final_font = load_font("Bold", 22)

    is_home_winner = game.home_score >= game.away_score

    draw.text((60, 70), "FINAL" if not game.went_to_shootout else "FINAL / SO", font=final_font, fill=Theme.TEXT_MUTED)
    if game.went_to_overtime and not game.went_to_shootout:
        draw.text((220, 72), "OT", font=final_font, fill=Theme.GOLD)

    draw.text((60, 140), home_team.name.upper(), font=name_font, fill=Theme.TEXT_PRIMARY if is_home_winner else Theme.TEXT_SECONDARY)
    draw.text((60, 230), str(game.home_score), font=score_font, fill=home_color)

    away_name = away_team.name.upper()
    away_name_w = draw.textlength(away_name, font=name_font)
    draw.text((WIDTH - 60 - away_name_w, 140), away_name, font=name_font, fill=Theme.TEXT_PRIMARY if not is_home_winner else Theme.TEXT_SECONDARY)
    away_score_str = str(game.away_score)
    away_score_w = draw.textlength(away_score_str, font=score_font)
    draw.text((WIDTH - 60 - away_score_w, 230), away_score_str, font=score_font, fill=away_color)

    draw.text((WIDTH // 2 - 14, 260), "-", font=score_font, fill=Theme.TEXT_MUTED)

    if is_home_winner:
        _draw_badge(draw, 60, 120, "W", Theme.WIN_GREEN)
    else:
        _draw_badge(draw, WIDTH - 60 - 28, 120, "W", Theme.WIN_GREEN, right_align=True)

    footer = "EASHL Match Imported via EA Pro Clubs"
    draw.text((60, HEIGHT - 50), footer, font=meta_font, fill=Theme.TEXT_MUTED)

    out_path = GENERATED_DIR / f"result_{uuid.uuid4().hex[:10]}.png"
    img.save(out_path)
    return str(out_path)


def _draw_badge(draw, x: int, y: int, text: str, color, right_align: bool = False) -> None:
    font = load_font("Bold", 16)
    pad = 8
    w = draw.textlength(text, font=font) + pad * 2
    x0 = x - w if right_align else x
    draw.rounded_rectangle([(x0, y), (x0 + w, y + 26)], radius=6, fill=color)
    draw.text((x0 + pad, y + 4), text, font=font, fill=(10, 10, 10))
