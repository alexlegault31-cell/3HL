"""
Centralized configuration for the NEHL bot.

All runtime configuration is pulled from environment variables / .env so the
same image can be deployed against different leagues / guilds without code
changes.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Discord
    discord_token: str
    discord_guild_id: int
    command_prefix: str = "!"

    channel_standings: int = 0
    channel_stat_leaders: int = 0
    channel_game_results: int = 0
    channel_schedule: int = 0
    channel_season_info: int = 0
    channel_awards: int = 0

    role_commissioner: str = "Commissioner"
    role_gm: str = "GM"

    # Database
    # Only DATABASE_URL is required. Railway (and most hosts) inject this as
    # a plain `postgresql://...` URL with no driver specified. We normalize
    # it to the asyncpg driver automatically, and derive sync_database_url
    # (used by Alembic, which needs psycopg2 instead of asyncpg) from it if
    # it isn't explicitly set. This means a single Railway "Reference
    # Variable" -> DATABASE_URL is enough; no manual URL surgery required.
    database_url: str
    sync_database_url: Optional[str] = None

    @model_validator(mode="after")
    def _normalize_db_urls(self) -> "Settings":
        self.database_url = _to_driver_url(self.database_url, "postgresql+asyncpg")
        if self.sync_database_url:
            self.sync_database_url = _to_driver_url(self.sync_database_url, "postgresql+psycopg2")
        else:
            self.sync_database_url = _to_driver_url(self.database_url, "postgresql+psycopg2")
        return self

    # ChelStats
    chelstats_base_url: str = "https://proclubs.ea.com/api/nhl"
    chelstats_api_key: str = ""
    chelstats_match_lookback: int = 20
    chelstats_platform: str = "common-gen5"
    chelstats_match_type: str = "club_private"

    # AI Recaps
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    recaps_enabled: bool = True

    # Misc
    timezone: str = "America/New_York"
    log_level: str = "INFO"

    @property
    def auto_update_channels(self) -> List[int]:
        return [
            cid
            for cid in (
                self.channel_standings,
                self.channel_stat_leaders,
                self.channel_game_results,
                self.channel_schedule,
                self.channel_season_info,
                self.channel_awards,
            )
            if cid
        ]


def _to_driver_url(url: str, driver_scheme: str) -> str:
    """Rewrite postgres://... or postgresql://... (and already-correct
    postgresql+asyncpg:// / postgresql+psycopg2:// URLs) to the requested
    driver scheme, leaving everything else about the URL untouched."""
    if "://" not in url:
        return url
    _, rest = url.split("://", 1)
    return f"{driver_scheme}://{rest}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
