"""Renders a player profile / season stats card for /league player stats."""
from __future__ import annotations

import uuid

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Player, PlayerSeason, Team

WIDTH, HEIGHT = 780, 440
LOGO_SIZE = 72
BANNER_H = 110


async def render_player_card(
    player: Player,
    season: PlayerSeason,
    team: Team | None,
    season_label: str,
    league_logo_url: str | None = None,
    background_url: str | None = None,
) -> str:
    accent = Theme.team_color(team) if team else Theme.ACCENT
    img, draw = await prepare_canvas(WIDTH, HEIGHT, accent, background_url, banner_height=BANNER_H)

    name_font = load_font("Black", 38)
    sub_font = load_font("Regular", 20)
    stat_label_font = load_font("Bold", 16)
    stat_val_font = load_font("Black", 34)
    role_font = load_font("Bold", 14)

    draw.text((32, 24), player.gamertag, font=name_font, fill=(255, 255, 255))
    role = "Goalie" if player.is_goalie else "Skater"
    team_line = f"{team.name} • {season_label} • {role}" if team else f"{season_label} • {role}"
    draw.text((34, 76), team_line, font=sub_font, fill=(210, 216, 230))

    logo = await get_team_logo(team.logo_url if team else None, (LOGO_SIZE, LOGO_SIZE))
    if logo is not None:
        img.paste(logo, (WIDTH - 32 - LOGO_SIZE, 20), logo.split()[-1])
    else:
        draw.ellipse([(WIDTH - 32 - LOGO_SIZE, 20), (WIDTH - 32, 20 + LOGO_SIZE)], fill=accent)
        role_letter = "G" if player.is_goalie else "S"
        rw = draw.textlength(role_letter, font=role_font)
        draw.text((WIDTH - 32 - LOGO_SIZE + (LOGO_SIZE - rw) / 2, 20 + LOGO_SIZE / 2 - 8), role_letter, font=role_font, fill=(10, 10, 10))

    league_logo = await get_team_logo(league_logo_url, (44, 44))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 32 - LOGO_SIZE - 56, 34), league_logo.split()[-1])

    if player.is_goalie:
        stats = [
            ("GP", str(season.games_played)),
            ("W-L-OTL", f"{season.wins}-{season.losses}-{season.ot_losses}"),
            ("GAA", f"{season.gaa:.2f}"),
            ("SV%", f"{season.save_pct:.3f}".lstrip("0")),
            ("SO", str(season.shutouts)),
            ("SAVES", str(season.saves)),
        ]
    else:
        stats = [
            ("GP", str(season.games_played)),
            ("G", str(season.goals)),
            ("A", str(season.assists)),
            ("PTS", str(season.points)),
            ("+/-", f"{'+' if season.plus_minus > 0 else ''}{season.plus_minus}"),
            ("PIM", str(season.pim)),
        ]

    cols = 3
    cell_w = (WIDTH - 56 * 2) // cols
    start_y = BANNER_H + 40
    for i, (label, value) in enumerate(stats):
        cx = 56 + (i % cols) * cell_w
        cy = start_y + (i // cols) * 110
        draw.text((cx, cy), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, cy + 22), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)
