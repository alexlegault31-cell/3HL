"""Renders a player profile card for /league player stats -- a season
summary up top, followed by a full per-game log (opponent, position, and
that game's stat line), instead of just season totals."""
from __future__ import annotations

import uuid

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Player, PlayerSeason, Team
from bot.services.game_log_service import GoalieGameLogRow, SkaterGameLogRow

WIDTH = 1040
LOGO_SIZE = 60
BANNER_H = 110
SUMMARY_H = 130
LOG_HEADER_H = 60
ROW_H = 32
OPP_LOGO_SIZE = 22
MAX_ROWS_SHOWN = 15

# Column x-positions for the skater game log table
SK_COLS = {
    "opp": 40, "pos": 330, "g": 400, "a": 460, "p": 520,
    "pm": 580, "sog": 650, "hits": 730, "pim": 810, "ta": 890,
}
# Column x-positions for the goalie game log table
GL_COLS = {"opp": 40, "result": 330, "sa": 420, "sv": 500, "ga": 580, "svpct": 660, "toi": 780}


async def render_player_card(
    player: Player,
    season: PlayerSeason,
    team: Team | None,
    season_label: str,
    league_logo_url: str | None = None,
    background_url: str | None = None,
    game_log: list | None = None,
) -> str:
    game_log = game_log or []
    rows_to_show = game_log[:MAX_ROWS_SHOWN]
    height = BANNER_H + SUMMARY_H + LOG_HEADER_H + ROW_H * max(len(rows_to_show), 1) + 40

    accent = Theme.team_color(team) if team else Theme.ACCENT
    img, draw = await prepare_canvas(WIDTH, height, accent, background_url, banner_height=BANNER_H)

    name_font = load_font("Black", 38)
    sub_font = load_font("Regular", 20)
    stat_label_font = load_font("Bold", 16)
    stat_val_font = load_font("Black", 32)
    role_font = load_font("Bold", 14)
    log_header_font = load_font("Bold", 15)
    log_row_font = load_font("Regular", 16)
    log_title_font = load_font("Black", 20)

    # --- Header banner ---
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

    league_logo = await get_team_logo(league_logo_url, (40, 40))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 32 - LOGO_SIZE - 50, 35), league_logo.split()[-1])

    # --- Season summary row ---
    summary_top = BANNER_H + 20
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
    cols = 6
    cell_w = (WIDTH - 64) // cols
    for i, (label, value) in enumerate(stats):
        cx = 32 + i * cell_w
        draw.text((cx, summary_top), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, summary_top + 22), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    # --- Game log ---
    log_top = BANNER_H + SUMMARY_H
    draw.line([(32, log_top), (WIDTH - 32, log_top)], fill=accent, width=2)
    draw.text((32, log_top + 10), "GAME LOG", font=log_title_font, fill=Theme.TEXT_PRIMARY)

    if not rows_to_show:
        draw.text((32, log_top + 44), "No games played yet this season.", font=log_row_font, fill=Theme.TEXT_MUTED)
        out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
        img.save(out_path)
        return str(out_path)

    header_y = log_top + 42
    cols_map = GL_COLS if player.is_goalie else SK_COLS
    headers = (
        {"opp": "OPPONENT", "result": "RESULT", "sa": "SA", "sv": "SV", "ga": "GA", "svpct": "SV%", "toi": "TOI"}
        if player.is_goalie
        else {"opp": "OPPONENT", "pos": "POS", "g": "G", "a": "A", "p": "P", "pm": "+/-", "sog": "SOG", "hits": "H", "pim": "PIM", "ta": "TA"}
    )
    for key, label in headers.items():
        draw.text((cols_map[key], header_y), label, font=log_header_font, fill=Theme.TEXT_MUTED)
    draw.line([(32, header_y + 24), (WIDTH - 32, header_y + 24)], fill=Theme.BORDER, width=1)

    y = header_y + 32
    logo_cache: dict[str, object] = {}  # avoid re-fetching the same opponent's logo for every row they appear in
    for i, row in enumerate(rows_to_show):
        if i % 2 == 1:
            draw.rectangle([(24, y - 4), (WIDTH - 24, y + ROW_H - 8)], fill=Theme.BG_PANEL)

        opp_url = row.opponent.logo_url if row.opponent else None
        if opp_url not in logo_cache:
            logo_cache[opp_url] = await get_team_logo(opp_url, (OPP_LOGO_SIZE, OPP_LOGO_SIZE))
        opp_logo = logo_cache[opp_url]
        name_x = cols_map["opp"]
        if opp_logo is not None:
            img.paste(opp_logo, (name_x, y - 2), opp_logo.split()[-1])
            name_x += OPP_LOGO_SIZE + 8
        vs = "vs" if row.is_home else "@"
        opp_name = row.opponent.name if row.opponent else "Unknown"
        draw.text((name_x, y), f"{vs} {opp_name}", font=log_row_font, fill=Theme.TEXT_PRIMARY)

        if player.is_goalie:
            result_color = Theme.WIN_GREEN if row.result == "W" else (Theme.GOLD if row.result == "OTL" else Theme.LOSS_RED)
            draw.text((cols_map["result"], y), row.result, font=log_row_font, fill=result_color)
            draw.text((cols_map["sa"], y), str(row.shots_against), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["sv"], y), str(row.saves), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ga"], y), str(row.goals_against), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            sv_pct = (row.saves / row.shots_against) if row.shots_against else 0.0
            draw.text((cols_map["svpct"], y), f"{sv_pct:.3f}".lstrip("0"), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            mins = int(row.minutes_played)
            secs = int(round((row.minutes_played - mins) * 60))
            draw.text((cols_map["toi"], y), f"{mins}:{secs:02d}", font=log_row_font, fill=Theme.TEXT_SECONDARY)
        else:
            draw.text((cols_map["pos"], y), (row.position or "-").upper()[:3], font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["g"], y), str(row.goals), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["a"], y), str(row.assists), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["p"], y), str(row.points), font=log_row_font, fill=Theme.TEXT_PRIMARY)
            pm_str = f"{'+' if row.plus_minus > 0 else ''}{row.plus_minus}"
            pm_color = Theme.WIN_GREEN if row.plus_minus > 0 else (Theme.LOSS_RED if row.plus_minus < 0 else Theme.TEXT_SECONDARY)
            draw.text((cols_map["pm"], y), pm_str, font=log_row_font, fill=pm_color)
            draw.text((cols_map["sog"], y), str(row.shots), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["hits"], y), str(row.hits), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pim"], y), str(row.pim), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ta"], y), str(row.takeaways), font=log_row_font, fill=Theme.TEXT_SECONDARY)

        y += ROW_H

    out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)
