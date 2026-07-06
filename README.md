# NEHL Discord League Bot

Discord-first hockey league management bot for NHL 26 / EASHL leagues, backed
by PostgreSQL. Pulls game stats automatically from ChelStats/ChelHead so
commissioners never manually enter goals/assists.

## Stack
Python 3.12 · discord.py 2.4 · SQLAlchemy 2.0 (async) · PostgreSQL · Alembic
· Pillow · OpenAI API · Docker

## Quick start

```bash
git clone <this repo> nehl-bot && cd nehl-bot
cp .env.example .env
# edit .env: DISCORD_TOKEN, DISCORD_GUILD_ID, channel IDs, CHELSTATS_BASE_URL, OPENAI_API_KEY

docker compose up --build
```

The `bot` service runs `alembic upgrade head` automatically before starting.
On first boot the bot syncs slash commands to your guild (instant, unlike
global sync).

Optional demo data:
```bash
docker compose exec bot python -m scripts.seed
```

## Configuring ChelStats/ChelHead

`bot/services/chelstats_client.py` is an adapter around whichever EASHL stats
mirror you use. Set `CHELSTATS_BASE_URL` / `CHELSTATS_API_KEY` in `.env`. If
the upstream JSON shape differs from what's assumed, only
`_normalize_match_summary` and `_normalize_match_detail` in that file need
to change — nothing else in the bot touches raw provider JSON.

## Command reference

**Setup (Commissioner)**
- `/season create number:3 name:"Season 3"`
- `/season activate number:3`
- `/team create name:Italy`
- `/team link-club team:Italy club_id:123456`
- `/schedule add game_number:50 home_team:Italy away_team:France week:5`

**Core workflow**
- `/entergame schedule_game_number:50` — GM/Commissioner. Looks up the
  schedule slot, resolves linked Club IDs, finds the matching EASHL match,
  imports the full box score, updates standings/records/leaders, generates
  an AI recap, and posts the result graphic to `#game-results`.
- `/game delete game_number:50` — reverses every stat/standings effect.
- `/game edit game_number:50 home_score:4 away_score:3` — manual score
  correction (team record only, not per-player lines).
- `/game ffw winning_team:Italy losing_team:France score:1-0 reason:"No-show"`

**Stats & standings**
- `/player link gamertag:YourGamertag`
- `/player stats [gamertag] [season]`
- `/player gamelog [gamertag] [season]`
- `/player card [gamertag] [season]`
- `/team stats team:Italy [season]`
- `/team history team:Italy [season]`
- `/team card team:Italy [season]`
- `/standings [season] [graphic]`
- `/leaders category:<goals|assists|points|goalie> [season] [graphic]`

**Schedule**
- `/schedule view [season]`
- `/schedule week week:5 [season]`
- `/schedule pending [season]`

**Awards**
- `/award create key:mvp display_name:"Most Valuable Player"`
- `/award give key:mvp gamertag:Toaster season:3`
- `/award list [season]`

## Permissions

Role names are configurable via `.env` (`ROLE_COMMISSIONER`, `ROLE_GM`).
- **Commissioner** — full control (or Discord Administrator permission)
- **GM** — `/entergame`, roster/team-scoped actions
- **Everyone** — stat lookups, `/player link`, schedule viewing

## Auto-updating channels

`bot/cogs/channel_updater.py` runs a 15-minute loop that regenerates the
standings and points-leaders graphics and edits-in-place in the channels set
by `CHANNEL_STANDINGS` / `CHANNEL_STAT_LEADERS` in `.env` (message id is
persisted in the `settings` table so it survives restarts).

## Database

Schema lives in `bot/models/` (SQLAlchemy ORM) with the source-of-truth
migration in `alembic/versions/0001_initial.py`. Everything is season-scoped
(`season_id` FK) — old seasons are never overwritten, only added to.

Generate a new migration after changing models:
```bash
docker compose exec bot alembic revision --autogenerate -m "describe change"
docker compose exec bot alembic upgrade head
```

## Project layout

```
bot/
  main.py                  entrypoint, loads cogs, syncs commands
  config.py                env-driven settings
  database.py               async SQLAlchemy engine/session
  models/                   ORM models (one file per domain area)
  services/
    chelstats_client.py     EASHL stats API adapter
    stat_importer.py        /entergame pipeline + /game delete reversal
    standings_service.py    standings recompute w/ tiebreakers
    leaders_service.py      stat leader queries
    recap_generator.py      OpenAI-powered game recaps
    season_service.py       active-season resolution helpers
    permissions_service.py  role-based permission checks
  graphics/                 Pillow-based PNG generators
  cogs/                     Discord slash command groups
  utils/                    embeds, permission-check decorators
alembic/                    migrations
scripts/seed.py              optional demo data
```
