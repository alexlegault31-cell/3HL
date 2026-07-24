"""Renders the full post-game recap graphic: header with score, a
team-vs-team stat comparison, and complete home/away rosters (same
per-game columns as the player card's game log) -- all in one combined
image with clear section dividers."""
from __future__ import annotations

import uuid

from bot.graphics.logo_fetch import get_team_logo
from bot.graphics.player_card import GL_COLS, GL_COLS_ORDER, GL_HEADERS, SK_COLS, SK_COLS_ORDER, SK_HEADERS, _fmt_toi
from bot.graphics.theme import GENERATED_DIR, Theme, load_font, prepare_canvas
from bot.models import Game, GoalieGameStat, Player, PlayerGameStat, Team, TeamGameStat

WIDTH = 1080
HEADER_H = 140
COMPARISON_ROW_H = 46
COMPARISON_TITLE_H = 50
ROSTER_HEADER_H = 50
ROSTER_ROW_H = 28
LOGO_SIZE = 64


def _truncate_to_fit(draw, text: str, font, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return (truncated + ellipsis) if truncated else ellipsis


def _passing_pct(pairs: list[tuple[Player, PlayerGameStat]]) -> float:
    attempts = sum(line.pass_attempts for _, line in pairs)
    completed = sum(line.passes_completed for _, line in pairs)
    return completed / attempts if attempts else 0.0


def _faceoffs_won(pairs: list[tuple[Player, PlayerGameStat]]) -> int:
    return sum(line.faceoffs_won for _, line in pairs)


async def render_game_recap(
    game: Game,
    home_team: Team,
    away_team: Team,
    home_team_stat: TeamGameStat,
    away_team_stat: TeamGameStat,
    home_skaters: list[tuple[Player, PlayerGameStat]],
    home_goalies: list[tuple[Player, GoalieGameStat]],
    away_skaters: list[tuple[Player, PlayerGameStat]],
    away_goalies: list[tuple[Player, GoalieGameStat]],
    league_logo_url: str | None = None,
    background_url: str | None = None,
) -> str:
    home_color = Theme.team_color(home_team, fallback=Theme.ACCENT)
    away_color = Theme.team_color(away_team, fallback=Theme.LOSS_RED)

    comparison_rows = 6  # Shots, Faceoffs Won, Hits, TOA, PIM, Passing%
    comparison_h = COMPARISON_TITLE_H + comparison_rows * COMPARISON_ROW_H + 20

    home_roster_h = ROSTER_HEADER_H + len(home_skaters) * ROSTER_ROW_H + (ROSTER_HEADER_H + len(home_goalies) * ROSTER_ROW_H if home_goalies else 0) + 30
    away_roster_h = ROSTER_HEADER_H + len(away_skaters) * ROSTER_ROW_H + (ROSTER_HEADER_H + len(away_goalies) * ROSTER_ROW_H if away_goalies else 0) + 30

    height = HEADER_H + comparison_h + home_roster_h + away_roster_h + 40

    img, draw = await prepare_canvas(WIDTH, height, home_color, background_url, banner_height=None)

    name_font = load_font("Black", 36)
    score_font = load_font("Black", 64)
    section_font = load_font("Black", 20)
    stat_label_font = load_font("Bold", 14)
    stat_val_font = load_font("Black", 22)
    row_header_font = load_font("Bold", 13)
    row_font = load_font("Regular", 14)

    # ================= HEADER =================
    draw.rectangle([(0, 0), (WIDTH // 2, 10)], fill=home_color)
    draw.rectangle([(WIDTH // 2, 0), (WIDTH, 10)], fill=away_color)

    home_logo = await get_team_logo(home_team.logo_url, (LOGO_SIZE, LOGO_SIZE))
    if home_logo is not None:
        img.paste(home_logo, (40, 38), home_logo.split()[-1])
    draw.text((40 + (LOGO_SIZE + 16 if home_logo else 0), 55), home_team.name, font=name_font, fill=Theme.TEXT_PRIMARY)

    away_name_w = draw.textlength(away_team.name, font=name_font)
    away_logo = await get_team_logo(away_team.logo_url, (LOGO_SIZE, LOGO_SIZE))
    away_logo_x = WIDTH - 40 - LOGO_SIZE
    if away_logo is not None:
        img.paste(away_logo, (away_logo_x, 38), away_logo.split()[-1])
    away_name_x = away_logo_x - 16 - away_name_w if away_logo else WIDTH - 40 - away_name_w
    draw.text((away_name_x, 55), away_team.name, font=name_font, fill=Theme.TEXT_PRIMARY)

    score_str = f"{game.home_score} - {game.away_score}"
    score_w = draw.textlength(score_str, font=score_font)
    draw.text(((WIDTH - score_w) / 2, 20), score_str, font=score_font, fill=(255, 255, 255))

    league_logo = await get_team_logo(league_logo_url, (36, 36))
    if league_logo is not None:
        img.paste(league_logo, (int((WIDTH - 36) / 2), 95), league_logo.split()[-1])

    # ================= TEAM COMPARISON =================
    comp_top = HEADER_H
    draw.line([(32, comp_top), (WIDTH - 32, comp_top)], fill=Theme.BORDER, width=2)
    draw.text((32, comp_top + 12), "TEAM COMPARISON", font=section_font, fill=Theme.TEXT_PRIMARY)

    home_pass_pct = _passing_pct(home_skaters)
    away_pass_pct = _passing_pct(away_skaters)
    home_fo = _faceoffs_won(home_skaters)
    away_fo = _faceoffs_won(away_skaters)

    comparisons = [
        ("SHOTS", home_team_stat.shots, away_team_stat.shots, False),
        ("FACEOFFS WON", home_fo, away_fo, False),
        ("HITS", home_team_stat.hits, away_team_stat.hits, False),
        ("TIME ON ATTACK", _fmt_toi(home_team_stat.time_on_attack), _fmt_toi(away_team_stat.time_on_attack), True),
        ("PIM", home_team_stat.pim, away_team_stat.pim, False),
        ("PASSING %", f"{home_pass_pct:.0%}", f"{away_pass_pct:.0%}", True),
    ]

    y = comp_top + COMPARISON_TITLE_H
    for label, home_val, away_val, is_preformatted in comparisons:
        # Determine which side "wins" this stat for bar-length emphasis
        # (skipped for preformatted string values like TOI/percentages,
        # which just render as plain centered text on each side).
        home_str = str(home_val)
        away_str = str(away_val)

        draw.text((32, y), home_str, font=stat_val_font, fill=home_color)
        label_w = draw.textlength(label, font=stat_label_font)
        draw.text(((WIDTH - label_w) / 2, y + 4), label, font=stat_label_font, fill=Theme.TEXT_MUTED)
        away_w = draw.textlength(away_str, font=stat_val_font)
        draw.text((WIDTH - 32 - away_w, y), away_str, font=stat_val_font, fill=away_color)

        if not is_preformatted:
            try:
                h, a = float(home_val), float(away_val)
                total = h + a
                if total > 0:
                    bar_w = WIDTH - 64
                    home_bar_w = int(bar_w * (h / total))
                    bar_y = y + 30
                    draw.rectangle([(32, bar_y), (32 + home_bar_w, bar_y + 4)], fill=home_color)
                    draw.rectangle([(32 + home_bar_w, bar_y), (WIDTH - 32, bar_y + 4)], fill=away_color)
            except (ValueError, TypeError):
                pass

        y += COMPARISON_ROW_H

    # ================= ROSTERS =================
    async def draw_roster(top: int, team: Team, skaters: list[tuple[Player, PlayerGameStat]], goalies: list[tuple[Player, GoalieGameStat]]) -> int:
        draw.line([(32, top), (WIDTH - 32, top)], fill=Theme.team_color(team), width=2)
        draw.text((32, top + 12), team.name.upper(), font=section_font, fill=Theme.TEXT_PRIMARY)
        y = top + ROSTER_HEADER_H

        if skaters:
            draw.text((32, y), "PLAYER", font=row_header_font, fill=Theme.TEXT_MUTED)
            for key in SK_COLS_ORDER:
                draw.text((SK_COLS[key], y), SK_HEADERS[key], font=row_header_font, fill=Theme.TEXT_MUTED)
            y += 20
            for i, (player, line) in enumerate(skaters):
                if i % 2 == 1:
                    draw.rectangle([(24, y - 3), (WIDTH - 24, y + ROSTER_ROW_H - 6)], fill=Theme.BG_PANEL)
                draw.text((32, y), _truncate_to_fit(draw, player.gamertag, row_font, SK_COLS["pos"] - 32 - 8), font=row_font, fill=Theme.TEXT_PRIMARY)
                draw.text((SK_COLS["pos"], y), (line.position or "-").upper()[:3], font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["g"], y), str(line.goals), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["a"], y), str(line.assists), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["p"], y), str(line.points), font=row_font, fill=Theme.TEXT_PRIMARY)
                pm_str = f"{'+' if line.plus_minus > 0 else ''}{line.plus_minus}"
                draw.text((SK_COLS["pm"], y), pm_str, font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["toi"], y), _fmt_toi(line.minutes_played), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["twp"], y), _fmt_toi(line.time_with_puck), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["shots"], y), str(line.shots), font=row_font, fill=Theme.TEXT_SECONDARY)
                pass_pct = (line.passes_completed / line.pass_attempts) if line.pass_attempts else 0.0
                draw.text((SK_COLS["pass"], y), f"{pass_pct:.0%}", font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["fow"], y), str(line.faceoffs_won), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["fol"], y), str(line.faceoffs_lost), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["h"], y), str(line.hits), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["ta"], y), str(line.takeaways), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["ga"], y), str(line.giveaways), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["bs"], y), str(line.blocked_shots), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["int"], y), str(line.interceptions), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((SK_COLS["pim"], y), str(line.pim), font=row_font, fill=Theme.TEXT_SECONDARY)
                y += ROSTER_ROW_H

        if goalies:
            y += 6
            draw.text((32, y), "GOALIE", font=row_header_font, fill=Theme.TEXT_MUTED)
            for key in GL_COLS_ORDER:
                draw.text((GL_COLS[key], y), GL_HEADERS[key], font=row_header_font, fill=Theme.TEXT_MUTED)
            y += 20
            for i, (player, line) in enumerate(goalies):
                if i % 2 == 1:
                    draw.rectangle([(24, y - 3), (WIDTH - 24, y + ROSTER_ROW_H - 6)], fill=Theme.BG_PANEL)
                draw.text((32, y), _truncate_to_fit(draw, player.gamertag, row_font, GL_COLS["result"] - 32 - 8), font=row_font, fill=Theme.TEXT_PRIMARY)
                result_str = "W" if line.result == 1 else ("OTL" if line.result == 2 else "L")
                result_color = Theme.WIN_GREEN if result_str == "W" else (Theme.GOLD if result_str == "OTL" else Theme.LOSS_RED)
                draw.text((GL_COLS["result"], y), result_str, font=row_font, fill=result_color)
                draw.text((GL_COLS["sa"], y), str(line.shots_against), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((GL_COLS["sv"], y), str(line.saves), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((GL_COLS["ga"], y), str(line.goals_against), font=row_font, fill=Theme.TEXT_SECONDARY)
                sv_pct = (line.saves / line.shots_against) if line.shots_against else 0.0
                draw.text((GL_COLS["svpct"], y), f"{sv_pct:.3f}".lstrip("0"), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((GL_COLS["toi"], y), _fmt_toi(line.minutes_played), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((GL_COLS["pkchk"], y), str(getattr(line, "poke_checks", 0)), font=row_font, fill=Theme.TEXT_SECONDARY)
                draw.text((GL_COLS["despsv"], y), str(getattr(line, "desperation_saves", 0)), font=row_font, fill=Theme.TEXT_SECONDARY)
                y += ROSTER_ROW_H

        return y + 20

    y = comp_top + comparison_h
    y = await draw_roster(y, home_team, home_skaters, home_goalies)
    await draw_roster(y, away_team, away_skaters, away_goalies)

    out_path = GENERATED_DIR / f"recap_{uuid.uuid4().hex[:8]}.png"
    img.save(out_path)
    return str(out_path)
