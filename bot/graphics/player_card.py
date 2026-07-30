"""Renders a player profile card for /league player stats -- a season
summary (labeled SKATER STATS / GOALIE STATS) followed by a full
per-game log. Includes the player's team logo and the league logo.

Shows a SKATER section and/or a GOALIE section based on whichever the
player actually has real game data for -- NOT based on a single
Player.is_goalie flag, since that flag gets overwritten on every import
to reflect whatever role they most recently played. A player who plays
both goalie and skater across a season (subbing, filling in shorthanded,
etc.) genuinely has both kinds of stats, and hiding one behind the other
would make real recorded stats invisible."""
from __future__ import annotations

import uuid

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.theme import GENERATED_DIR, Theme, finalize_and_save, load_font, prepare_canvas
from bot.models import Player, PlayerSeason, Team

WIDTH = 1080
BANNER_H = 100
SUMMARY_H = 110
LOG_HEADER_H = 56
ROW_H = 30
MAX_ROWS_SHOWN = 15

SK_COLS_ORDER = ["pos", "g", "a", "p", "pm", "toi", "twp", "shots", "pass", "fow", "fol", "h", "ta", "ga", "bs", "int", "pim"]
SK_HEADERS = {
    "pos": "POS", "g": "G", "a": "A", "p": "P", "pm": "+/-", "toi": "TOI", "twp": "TwP",
    "shots": "SOG", "pass": "PS%", "fow": "FOW", "fol": "FOL", "h": "H", "ta": "TA",
    "ga": "GA", "bs": "BS", "int": "INT", "pim": "PIM",
}

GL_COLS_ORDER = ["result", "sa", "sv", "ga", "svpct", "toi", "pkchk", "despsv"]
GL_HEADERS = {
    "result": "RESULT", "sa": "SA", "sv": "SV", "ga": "GA", "svpct": "SV%",
    "toi": "TOI", "pkchk": "PKCHK", "despsv": "DESPSV",
}

OPP_COL_W = 190


def _col_positions(order: list[str]) -> dict[str, int]:
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


def _truncate_to_fit(draw, text: str, font, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return (truncated + ellipsis) if truncated else ellipsis


def _aggregate_skater(rows: list) -> dict:
    gp = len(rows)
    points = sum(r.points for r in rows)
    return {
        "gp": gp,
        "goals": sum(r.goals for r in rows),
        "assists": sum(r.assists for r in rows),
        "points": points,
        "ppg": (points / gp) if gp else 0.0,
        "plus_minus": sum(r.plus_minus for r in rows),
        "pim": sum(r.pim for r in rows),
        "hits": sum(r.hits for r in rows),
    }


def _aggregate_goalie(rows: list) -> dict:
    total_sa = sum(r.shots_against for r in rows)
    total_sv = sum(r.saves for r in rows)
    total_ga = sum(r.goals_against for r in rows)
    total_min = sum(r.minutes_played for r in rows)
    return {
        "gp": len(rows),
        "shots_against": total_sa,
        "goals_against": total_ga,
        "saves": total_sv,
        "save_pct": (total_sv / total_sa) if total_sa else 0.0,
        "gaa": (total_ga / (total_min / 60)) if total_min else 0.0,
        "shutouts": sum(1 for r in rows if r.shutout),
    }


def _section_height(game_log: list) -> int:
    rows_to_show = game_log[:MAX_ROWS_SHOWN]
    return SUMMARY_H + LOG_HEADER_H + ROW_H * max(len(rows_to_show), 1)


def _draw_section(img, draw, y_top: int, is_goalie: bool, game_log: list, fonts: dict, accent) -> None:
    """Draws one full section (stat summary + game log) for a single
    role, starting at y_top. Identical layout/logic to what this file
    always had -- just extracted into a reusable block so it can be
    called once (the common single-role case) or twice (a player who
    has real data in both roles this season)."""
    regular_rows = [r for r in game_log if not r.is_playoffs]
    playoff_rows = [r for r in game_log if r.is_playoffs]

    summary_top = y_top + 14
    section_label = "GOALIE STATS" if is_goalie else "SKATER STATS"
    draw.text((32, summary_top), section_label, font=fonts["section_label"], fill=Theme.TEXT_PRIMARY)

    has_playoffs = len(playoff_rows) > 0
    row_y = summary_top + 44

    if has_playoffs:
        half_w = (WIDTH - 64 - 32) // 2
        left_x = 32
        right_x = 32 + half_w + 32
        divider_x = right_x - 16
        draw.line([(divider_x, row_y - 6), (divider_x, row_y + 52)], fill=Theme.BORDER, width=1)
    else:
        half_w = WIDTH - 64
        left_x = 32
        right_x = None

    def _stat_block(x: int, block_w: int, heading: str, rows: list) -> None:
        draw.text((x, row_y - 22), heading, font=fonts["stat_label"], fill=Theme.TEXT_MUTED)
        if not rows:
            draw.text((x, row_y + 4), "No games yet", font=fonts["stat_label"], fill=Theme.TEXT_MUTED)
            return
        if is_goalie:
            agg = _aggregate_goalie(rows)
            stats = [
                ("SA", str(agg["shots_against"])), ("GA", str(agg["goals_against"])), ("SV", str(agg["saves"])),
                ("SV%", f"{agg['save_pct']:.3f}".lstrip("0")), ("GAA", f"{agg['gaa']:.2f}"), ("SO", str(agg["shutouts"])),
            ]
        else:
            agg = _aggregate_skater(rows)
            stats = [
                ("G", str(agg["goals"])), ("A", str(agg["assists"])), ("P", str(agg["points"])), ("PPG", f"{agg['ppg']:.2f}"),
                ("+/-", f"{'+' if agg['plus_minus'] > 0 else ''}{agg['plus_minus']}"), ("PIM", str(agg["pim"])), ("HITS", str(agg["hits"])),
            ]
        cell_w = block_w // len(stats)
        for i, (label, value) in enumerate(stats):
            cx = x + i * cell_w
            draw.text((cx, row_y), label, font=fonts["stat_label"], fill=Theme.TEXT_MUTED)
            draw.text((cx, row_y + 20), value, font=fonts["stat_val_smaller"], fill=Theme.TEXT_PRIMARY)

    _stat_block(left_x, half_w, f"REGULAR SEASON ({len(regular_rows)} GP)", regular_rows)
    if has_playoffs:
        _stat_block(right_x, half_w, f"PLAYOFFS ({len(playoff_rows)} GP)", playoff_rows)

    # --- Game log ---
    log_top = y_top + SUMMARY_H
    draw.line([(32, log_top), (WIDTH - 32, log_top)], fill=accent, width=2)
    draw.text((32, log_top + 8), section_label + " GAME LOG", font=fonts["log_title"], fill=Theme.TEXT_PRIMARY)

    rows_to_show = game_log[:MAX_ROWS_SHOWN]
    if not rows_to_show:
        draw.text((32, log_top + 40), "No games played yet.", font=fonts["log_row"], fill=Theme.TEXT_MUTED)
        return

    header_y = log_top + 38
    cols_order = GL_COLS_ORDER if is_goalie else SK_COLS_ORDER
    cols_map = GL_COLS if is_goalie else SK_COLS
    headers = GL_HEADERS if is_goalie else SK_HEADERS

    draw.text((32, header_y), "OPPONENT", font=fonts["log_header"], fill=Theme.TEXT_MUTED)
    for key in cols_order:
        draw.text((cols_map[key], header_y), headers[key], font=fonts["log_header"], fill=Theme.TEXT_MUTED)
    draw.line([(32, header_y + 20), (WIDTH - 32, header_y + 20)], fill=Theme.BORDER, width=1)

    y = header_y + 26
    for i, row in enumerate(rows_to_show):
        if i % 2 == 1:
            draw.rectangle([(24, y - 3), (WIDTH - 24, y + ROW_H - 6)], fill=Theme.BG_PANEL)

        vs = "vs" if row.is_home else "@"
        opp_name = row.opponent.name if row.opponent else "Unknown"
        draw.text((32, y), _truncate_to_fit(draw, f"{vs} {opp_name}", fonts["log_row"], OPP_COL_W - 8), font=fonts["log_row"], fill=Theme.TEXT_PRIMARY)

        if is_goalie:
            result_color = Theme.WIN_GREEN if row.result == "W" else (Theme.GOLD if row.result == "OTL" else Theme.LOSS_RED)
            draw.text((cols_map["result"], y), row.result, font=fonts["log_row"], fill=result_color)
            draw.text((cols_map["sa"], y), str(row.shots_against), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["sv"], y), str(row.saves), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ga"], y), str(row.goals_against), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["svpct"], y), f"{row.save_pct:.3f}".lstrip("0"), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["toi"], y), _fmt_toi(row.minutes_played), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pkchk"], y), str(row.poke_checks), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["despsv"], y), str(row.desperation_saves), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
        else:
            draw.text((cols_map["pos"], y), (row.position or "-").upper()[:3], font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["g"], y), str(row.goals), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["a"], y), str(row.assists), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["p"], y), str(row.points), font=fonts["log_row"], fill=Theme.TEXT_PRIMARY)
            pm_str = f"{'+' if row.plus_minus > 0 else ''}{row.plus_minus}"
            pm_color = Theme.WIN_GREEN if row.plus_minus > 0 else (Theme.LOSS_RED if row.plus_minus < 0 else Theme.TEXT_SECONDARY)
            draw.text((cols_map["pm"], y), pm_str, font=fonts["log_row"], fill=pm_color)
            draw.text((cols_map["toi"], y), _fmt_toi(row.minutes_played), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["twp"], y), _fmt_toi(row.time_with_puck), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["shots"], y), str(row.shots), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pass"], y), f"{row.pass_pct:.0%}", font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["fow"], y), str(row.faceoffs_won), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["fol"], y), str(row.faceoffs_lost), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["h"], y), str(row.hits), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ta"], y), str(row.takeaways), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["ga"], y), str(row.giveaways), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["bs"], y), str(row.blocked_shots), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["int"], y), str(row.interceptions), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
            draw.text((cols_map["pim"], y), str(row.pim), font=fonts["log_row"], fill=Theme.TEXT_SECONDARY)
        y += ROW_H


async def render_player_card(
    player: Player,
    season: PlayerSeason,
    team: Team | None,
    season_label: str,
    league_logo_url: str | None = None,
    background_url: str | None = None,
    skater_game_log: list | None = None,
    goalie_game_log: list | None = None,
) -> str:
    skater_game_log = skater_game_log or []
    goalie_game_log = goalie_game_log or []
    show_skater = len(skater_game_log) > 0
    show_goalie = len(goalie_game_log) > 0

    if not show_skater and not show_goalie:
        show_skater = True  # never-played-a-game fallback -- show an empty skater section rather than a blank card

    sections_height = 0
    if show_goalie:
        sections_height += _section_height(goalie_game_log)
    if show_skater:
        sections_height += _section_height(skater_game_log)

    height = BANNER_H + sections_height + 40

    accent = Theme.team_color(team) if team else Theme.ACCENT
    img, draw = await prepare_canvas(WIDTH, height, accent, background_url, banner_height=BANNER_H)

    fonts = {
        "name": load_font("Black", 34),
        "sub": load_font("Regular", 18),
        "section_label": load_font("Black", 18),
        "stat_label": load_font("Bold", 14),
        "stat_val": load_font("Black", 28),
        "stat_val_smaller": load_font("Black", 22),
        "log_header": load_font("Bold", 13),
        "log_row": load_font("Regular", 14),
        "log_title": load_font("Black", 18),
    }

    draw.text((32, 20), player.gamertag, font=fonts["name"], fill=(255, 255, 255))
    role = "Goalie" if (show_goalie and not show_skater) else ("Skater" if (show_skater and not show_goalie) else "Goalie / Skater")
    team_line = f"{team.name} • {season_label} • {role}" if team else f"{season_label} • {role}"

    team_line_x = 34
    if team is not None:
        team_logo = await get_team_logo(team.logo_url, (28, 28))
        if team_logo is not None:
            img.paste(team_logo, (34, 60), team_logo.split()[-1])
            team_line_x = 34 + 28 + 8
    draw.text((team_line_x, 66), team_line, font=fonts["sub"], fill=(210, 216, 230))

    league_logo = await get_team_logo(league_logo_url, (60, 60))
    if league_logo is not None:
        img.paste(league_logo, (WIDTH - 40 - 60, 20), league_logo.split()[-1])

    y = BANNER_H
    if show_goalie:
        _draw_section(img, draw, y, True, goalie_game_log, fonts, accent)
        y += _section_height(goalie_game_log)
    if show_skater:
        _draw_section(img, draw, y, False, skater_game_log, fonts, accent)

    out_path = GENERATED_DIR / f"player_{player.id}_{uuid.uuid4().hex[:8]}.png"
    finalize_and_save(img, out_path)
    return str(out_path)
