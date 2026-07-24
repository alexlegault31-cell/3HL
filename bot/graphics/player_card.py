"""Renders a player profile card for /league player stats -- a season
summary (labeled SKATER STATS / GOALIE STATS) followed by a full
per-game log. No team/league logos are drawn on this card by request."""
from __future__ import annotations

import uuid

from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Player, PlayerSeason, Team

WIDTH = 1080
BANNER_H = 100
SUMMARY_H = 110
LOG_HEADER_H = 56
ROW_H = 30
MAX_ROWS_SHOWN = 15

# Column x-positions for the skater game log table -- order matches the
# exact spec: Position, G, A, P, +/-, TOI, TwP, Shots, Pass%, FOW, FOL,
# H, TA, GA (giveaways), BS, INT, PIM
SK_COLS_ORDER = ["pos", "g", "a", "p", "pm", "toi", "twp", "shots", "pass", "fow", "fol", "h", "ta", "ga", "bs", "int", "pim"]
SK_HEADERS = {
    "pos": "POS", "g": "G", "a": "A", "p": "P", "pm": "+/-", "toi": "TOI", "twp": "TwP",
    "shots": "SOG", "pass": "PS%", "fow": "FOW", "fol": "FOL", "h": "H", "ta": "TA",
    "ga": "GA", "bs": "BS", "int": "INT", "pim": "PIM",
}

# Goalie per-game log columns
GL_COLS_ORDER = ["result", "sa", "sv", "ga", "svpct", "toi", "pkchk", "despsv"]
GL_HEADERS = {
    "result": "RESULT", "sa": "SA", "sv": "SV", "ga": "GA", "svpct": "SV%",
    "toi": "TOI", "pkchk": "PKCHK", "despsv": "DESPSV",
}

OPP_COL_W = 190


def _col_positions(order: list[str]) -> dict[str, int]:
    """Evenly distributes the remaining width after the opponent column
    across every stat column in the given order."""
    available = WIDTH - 64 - OPP_COL_W
    col_w = available // len(order)
    positions = {}
    x = 32 + OPP_COL_W
    for key in order:
        positions[key] = x
        x += col_w
    return positions


SK_COLS = _col_positions(SK_COLS_ORDER)
GL_COLS = _col_positions(GL_COLS_ORDER)


def _fmt_toi(minutes: float) -> str:
    mins = int(minutes)
    secs = int(round((minutes - mins) * 60))
    return f"{mins}:{secs:02d}"


async def render_player_card(
    player: Player,
    season: PlayerSeason,
    team: Team | None,
    season_label: str,
    league_logo_url: str | None = None,  # accepted for call-site compatibility, intentionally unused -- no logos on this card
    background_url: str | None = None,
    game_log: list | None = None,
) -> str:
    game_log = game_log or []
    rows_to_show = game_log[:MAX_ROWS_SHOWN]
    height = BANNER_H + SUMMARY_H + LOG_HEADER_H + ROW_H * max(len(rows_to_show), 1) + 40

    accent = Theme.team_color(team) if team else Theme.ACCENT
    img, draw = await prepare_canvas(WIDTH, height, accent, background_url, banner_height=BANNER_H)

    name_font = load_font("Black", 34)
    sub_font = load_font("Regular", 18)
    section_label_font = load_font("Black", 18)
    stat_label_font = load_font("Bold", 14)
    stat_val_font = load_font("Black", 28)
    role_font = load_font("Bold", 13)
    log_header_font = load_font("Bold", 13)
    log_row_font = load_font("Regular", 14)
    log_title_font = load_font("Black", 18)

    # --- Header banner (no logos) ---
    draw.text((32, 20), player.gamertag, font=name_font, fill=(255, 255, 255))
    role = "Goalie" if player.is_goalie else "Skater"
    team_line = f"{team.name} • {season_label} • {role}" if team else f"{season_label} • {role}"
    draw.text((34, 64), team_line, font=sub_font, fill=(210, 216, 230))

    # --- Season summary ---
    summary_top = BANNER_H + 14
    section_label = "GOALIE STATS" if player.is_goalie else "SKATER STATS"
    draw.text((32, summary_top), section_label, font=section_label_font, fill=Theme.TEXT_PRIMARY)

    if player.is_goalie:
        stats = [
            ("SHOTS", str(season.shots_against)),
            ("GA", str(season.goals_against)),
            ("SAVES", str(season.saves)),
            ("SAVE%", f"{season.save_pct:.3f}".lstrip("0")),
            ("GAA", f"{season.gaa:.2f}"),
            ("PKCHK", str(getattr(season, "poke_checks", 0))),
            ("DESPSAVE", str(getattr(season, "desperation_saves", 0))),
        ]
    else:
        stats = [
            ("GOALS", str(season.goals)),
            ("ASSISTS", str(season.assists)),
            ("POINTS", str(season.points)),
            ("PPG", str(season.ppg)),
            ("+/-", f"{'+' if season.plus_minus > 0 else ''}{season.plus_minus}"),
            ("PIM", str(season.pim)),
            ("HITS", str(season.hits)),
        ]
    cols = len(stats)
    cell_w = (WIDTH - 64) // cols
    row_y = summary_top + 30
    for i, (label, value) in enumerate(stats):
        cx = 32 + i * cell_w
        draw.text((cx, row_y), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        draw.text((cx, row_y + 20), value, font=stat_val_font, fill=Theme.TEXT_PRIMARY)

    # --- Game log ---
    log_top = BANNER_H + SUMMARY_H
    draw.line([(32, log_top), (WIDTH - 32, log_top)], fill=accent, width=2)
    draw.text((32, log_top + 8), f"GAME LOG - {season_label}", font=log_title_font, fill=Theme.TEXT_PRIMARY)

    if not rows_to_show:
        draw.text((32, log_top + 40), "No games played yet this season.", font=log_row_font, fill=Theme.TEXT_MUTED)
        out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
        img.save(out_path)
        return str(out_path)

    header_y = log_top + 38
    cols_order = GL_COLS_ORDER if player.is_goalie else SK_COLS_ORDER
    cols_map = GL_COLS if player.is_goalie else SK_COLS
    headers = GL_HEADERS if player.is_goalie else SK_HEADERS

    draw.text((32, header_y), "OPPONENT", font=log_header_font, fill=Theme.TEXT_MUTED)
    for key in cols_order:
        draw.text((cols_map[key], header_y), headers[key], font=log_header_font, fill=Theme.TEXT_MUTED)
    draw.line([(32, header_y + 20), (WIDTH - 32, header_y + 20)], fill=Theme.BORDER, width=1)

    y = header_y + 26
    for i, row in enumerate(rows_to_show):
        if i % 2 == 1:
            draw.rectangle([(24, y - 3), (WIDTH - 24, y + ROW_H - 6)], fill=Theme.BG_PANEL)

        vs = "vs" if row.is_home else "@"
        opp_name = row.opponent.name if row.opponent else "Unknown"
        draw.text((32, y), f"{vs} {opp_name}", font=log_row_font, fill=Theme.TEXT_PRIMARY)

        if player.is_goalie:
            result_color = Theme.WIN_GREEN if row.result == "W" else (Theme.GOLD if row.result == "OTL" else Theme.LOSS_RED)
            draw.text((cols_map["result"], y), row.result, font=log_row_font, fill=result_color)
            draw.text((cols_map["sa"], y), str(row.shots_against), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["sv"], y), str(row.saves), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ga"], y), str(row.goals_against), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["svpct"], y), f"{row.save_pct:.3f}".lstrip("0"), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["toi"], y), _fmt_toi(row.minutes_played), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pkchk"], y), str(row.poke_checks), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["despsv"], y), str(row.desperation_saves), font=log_row_font, fill=Theme.TEXT_SECONDARY)
        else:
            draw.text((cols_map["pos"], y), (row.position or "-").upper()[:3], font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["g"], y), str(row.goals), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["a"], y), str(row.assists), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["p"], y), str(row.points), font=log_row_font, fill=Theme.TEXT_PRIMARY)
            pm_str = f"{'+' if row.plus_minus > 0 else ''}{row.plus_minus}"
            pm_color = Theme.WIN_GREEN if row.plus_minus > 0 else (Theme.LOSS_RED if row.plus_minus < 0 else Theme.TEXT_SECONDARY)
            draw.text((cols_map["pm"], y), pm_str, font=log_row_font, fill=pm_color)
            draw.text((cols_map["toi"], y), _fmt_toi(row.minutes_played), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["twp"], y), _fmt_toi(row.time_with_puck), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["shots"], y), str(row.shots), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pass"], y), f"{row.pass_pct:.0%}", font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["fow"], y), str(row.faceoffs_won), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["fol"], y), str(row.faceoffs_lost), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["h"], y), str(row.hits), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ta"], y), str(row.takeaways), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ga"], y), str(row.giveaways), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["bs"], y), str(row.blocked_shots), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["int"], y), str(row.interceptions), font=log_row_font, fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pim"], y), str(row.pim), font=log_row_font, fill=Theme.TEXT_SECONDARY)

        y += ROW_H

    out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)
