FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: libpq for psycopg2, fonts + freetype for Pillow text rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway (and most single-service hosts) run the Dockerfile CMD directly and
# do NOT honor docker-compose.yml's `command:` override, so migrations have
# to run here, not just in compose. `entrypoint.sh` runs `alembic upgrade
# head` then execs the bot, so this Dockerfile behaves identically whether
# it's run via `docker compose up`, `docker run`, or a Railway deploy.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
