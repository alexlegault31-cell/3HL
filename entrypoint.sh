#!/bin/sh
# Runs before the bot process on every container start (local docker-compose
# AND Railway/Render/Fly/etc, since this is baked into the image itself
# rather than a docker-compose command override that only compose reads).
set -e

echo "[entrypoint] Running database migrations..."
alembic upgrade head

echo "[entrypoint] Starting bot..."
exec python -m bot.main
