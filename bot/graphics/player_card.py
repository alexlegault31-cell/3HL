
"""Renders a player profile / season stats card for /player card."""
from __future__ import annotations

import uuid

from PIL import Image, ImageDraw

from bot.graphics.theme import GENERATED_DIR, Theme, load_font
from bot.models import Player, PlayerSeason, Team

WIDTH, HEIGHT = 760, 420


def render_player_card(player: Player, season: PlayerSeason, team: Team | None, season_label: str) -> str:
    img = Image.new("RGB", (WIDTH, HEIGHT), Theme.BG_DARK)
    draw = ImageDraw.Draw(img)

    accent = Theme.team_color(team) if team else Theme.ACCENT
    draw.rectangle([(0, 0), (WIDTH, 10)], fill=accent)
    draw.rounded_rectangle([(24, 30), (WIDTH - 24, HEIGHT - 24)], radius=18, fill=Theme.BG_PANEL, outline=Theme.BORDER, width=1)

    name_font = load_font("Black", 38)
    sub_font = load_font("Regular", 20)
    stat_label_font = load_font("Bold", 16)
    stat_val_font = load_font("Black", 34)

    draw.text((56, 58), player.gamertag, font=name_font, fill=Theme.TEXT_PRIMARY)
    team_line = f"{team.name} • {season_label}" if team else season_label
    draw.text((58, 108), team_line, font=sub_font, fill=Theme.TEXT_SECONDARY)
    role = "Goalie" if player.is_goalie else "Skater"
    draw.ellipse([(WIDTH - 110, 58), (WIDTH - 56, 112)], fill=accent)
    role_font = load_font("Bold", 14)
    rw = draw.textlength(role[0], font=role_font)
    draw.text((WIDTH - 110 + (54 - rw) / 2, 70), role[0], font=role_font, fill=(10, 10, 10))

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
    start_y = 200
    for i, (label, value) in enumerate(stats):
        cx = 56 + (i % cols) * cell_w
        cy = start_y + (i // cols) * 110
        draw.text((cx, cy), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, cy + 22), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)

