"""SamayModeManager — the spec's mode interface.

    manager = SamayModeManager()                # builds the base clone once
    manager.get_casual_samay()                  # ~800-1200, impulsive
    manager.get_real_samay()                    # the authentic clone
    manager.get_peak_samay()                    # locked-in
    manager.get_adaptive_samay(user_rating)     # matched to the user

camelCase aliases (`getCasualSamay`, ...) are provided to match the spec
verbatim. The generic `CloneModeManager` underneath works for any username, so
mode support extends to every future clone for free.

The expensive base clone (repertoire snapshot + profile) is built once and
shared; each mode getter returns a lightweight `ModedCloneProvider` view over
it, so switching modes mid-session is instant.
"""

from __future__ import annotations

import random
from typing import Optional

from player_clones.db import Database
from player_clones.providers.factory import create_player_clone
from player_clones.providers.base_provider import CloneProvider
from player_clones.modes.mode_config import (
    ModeConfig, CASUAL, REAL, PEAK, MODE_PRESETS, adaptive_config,
)
from player_clones.modes.moded_provider import ModedCloneProvider


class CloneModeManager:
    """Mode views over a single base clone for any Chess.com username."""

    def __init__(self, username: str, db: Optional[Database] = None,
                 source: str = "auto", rng: Optional[random.Random] = None):
        self.username = username
        self._rng = rng
        self._base = create_player_clone(username, db=db, source=source, rng=rng)

    # ----- generic access ------------------------------------------------- #
    def get(self, mode_key: str, user_rating: int = 1200) -> CloneProvider:
        if mode_key == "adaptive":
            return self._moded(adaptive_config(user_rating))
        preset = MODE_PRESETS.get(mode_key)
        if preset is None:
            raise KeyError(f"unknown mode: {mode_key!r} "
                           f"(expected one of {sorted(MODE_PRESETS)} or 'adaptive')")
        return self._moded(preset)

    def base(self) -> CloneProvider:
        """The undecorated clone (used by the DNA page)."""
        return self._base

    def _moded(self, config: ModeConfig) -> ModedCloneProvider:
        return ModedCloneProvider(self._base, config, rng=self._rng)

    # ----- spec interface -------------------------------------------------- #
    def get_casual_samay(self) -> CloneProvider:
        return self._moded(CASUAL)

    def get_real_samay(self) -> CloneProvider:
        return self._moded(REAL)

    def get_peak_samay(self) -> CloneProvider:
        return self._moded(PEAK)

    def get_adaptive_samay(self, user_rating: int) -> CloneProvider:
        return self._moded(adaptive_config(user_rating))

    # camelCase aliases, verbatim per spec
    getCasualSamay = get_casual_samay
    getRealSamay = get_real_samay
    getPeakSamay = get_peak_samay
    getAdaptiveSamay = get_adaptive_samay


class SamayModeManager(CloneModeManager):
    """`CloneModeManager` pre-bound to samayraina."""

    def __init__(self, db: Optional[Database] = None, source: str = "auto",
                 rng: Optional[random.Random] = None):
        super().__init__("samayraina", db=db, source=source, rng=rng)
