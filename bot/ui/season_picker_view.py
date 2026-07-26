"""Reusable 'which season?' dropdown -- used by /league club stats and
/league player stats when no season number is given directly, so people
can browse any past season without needing to know its number."""
from __future__ import annotations

from typing import Awaitable, Callable

import discord


class SeasonPickerView(discord.ui.View):
    def __init__(self, seasons: list, on_select: Callable[[discord.Interaction, int], Awaitable[None]]):
        super().__init__(timeout=120)
        self._on_select = on_select

        select = discord.ui.Select(
            placeholder="Which season would you like to see?",
            options=[discord.SelectOption(label=s.name, value=str(s.id)) for s in seasons[:25]],
        )
        select.callback = self._callback
        self._select = select
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction) -> None:
        season_id = int(self._select.values[0])
        await self._on_select(interaction, season_id)
