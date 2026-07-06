################################################################
FILE PATH TO TYPE ON GITHUB: scripts/seed.py
################################################################
"""
Optional convenience script: creates Season 1, two demo teams, and links
placeholder Club IDs, matching the example in the spec (Italy/France).

Run with: python -m scripts.seed
"""
from __future__ import annotations

import asyncio

from bot.database import get_session
from bot.models import Season, Team, TeamSeason


async def seed():
    async with get_session() as session:
        season = Season(number=1, name="Season 1", is_active=True)
        session.add(season)
        await session.flush()

        italy = Team(name="Italy", abbreviation="ITA", primary_color="#008C45")
        france = Team(name="France", abbreviation="FRA", primary_color="#0055A4")
        session.add_all([italy, france])
        await session.flush()

        session.add(TeamSeason(team_id=italy.id, season_id=season.id, club_id=123456))
        session.add(TeamSeason(team_id=france.id, season_id=season.id, club_id=654321))

    print("Seeded Season 1 with Italy (Club 123456) and France (Club 654321).")


if __name__ == "__main__":
    asyncio.run(seed())

===== END OF FILE, COPY UP TO HERE =====
