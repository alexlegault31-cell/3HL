"""Reusable 'which team?' dropdown -- shows every team that actually
participated in a given season (via TeamSeason), including inactive/
legacy teams that wouldn't show up in the normal autocomplete."""
from __future__ import annotations

from typing import Awaitable, Callable

import discord


class TeamPickerView(discord.ui.View):
    def __init__(self, teams: list, on_select: Callable[[discord.Interaction, int], Awaitable[None]]):
        super().__init__(timeout=120)
        self._on_select = on_select

        select = discord.ui.Select(
            placeholder="Which team would you like to see?",
            options=[discord.SelectOption(label=t.name, value=str(t.id)) for t in teams[:25]],
        )
        select.callback = self._callback
        self._select = select
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction) -> None:
        team_id = int(self._select.values[0])
        await self._on_select(interaction, team_id)
