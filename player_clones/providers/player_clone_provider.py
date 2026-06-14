"""PlayerCloneProvider — a ready-to-play clone for ANY username (PHASE 5).

Wraps a `StyleProfile` + a `PlayerCloneEngine` wired to the player's stored
repertoire. Construction is cheap; all the heavy lifting (import, parse,
analyze) is done by the factory before this object exists, so the provider just
serves moves and style data.
"""

from __future__ import annotations

import random
from typing import Optional

from engine import State, Move
from player_clones.db import Database
from player_clones.models import Player, StyleProfile
from player_clones.clone_engine.clone_engine import PlayerCloneEngine, CloneDecision
from player_clones.clone_engine.candidate_provider import CandidateProvider
from player_clones.providers.base_provider import CloneProvider


class PlayerCloneProvider(CloneProvider):
    def __init__(self, db: Database, player: Player, profile: StyleProfile,
                 candidate_depth: int = 3,
                 rng: Optional[random.Random] = None,
                 repertoire: Optional[dict] = None,
                 total_games: Optional[int] = None):
        self._db = db
        self._player = player
        self._profile = profile
        # Snapshot the repertoire + game count once, in-memory. Move selection
        # then never touches SQLite — important because the GUI drives the clone
        # from background threads (SQLite connections are not thread-portable).
        #
        # `repertoire`/`total_games` may be injected directly (e.g. loaded from a
        # precomputed deployment artifact) so the provider can run without the
        # full games database — see player_clones/book.py.
        self._repertoire = (repertoire if repertoire is not None
                            else db.moves.repertoire(player.id))
        self._total_games = (total_games if total_games is not None
                             else db.games.count(player.id))
        self._engine = PlayerCloneEngine(
            profile,
            repertoire_lookup=lambda key: self._repertoire.get(key, []),
            candidate_provider=CandidateProvider(depth=candidate_depth),
            rng=rng,
        )

    # ----- identity ----------------------------------------------------- #
    @property
    def username(self) -> str:
        return self._player.username

    @property
    def display_name(self) -> str:
        return f"{self._player.display_name} Style Clone"

    @property
    def profile(self) -> StyleProfile:
        return self._profile

    # ----- gameplay ----------------------------------------------------- #
    def choose_move(self, state: State) -> Optional[Move]:
        return self._engine.choose_move(state)

    def decide(self, state: State) -> CloneDecision:
        return self._engine.decide(state)

    def reset(self) -> None:
        self._engine.influence.clear()

    def influence_summary(self):
        return self._engine.influence_summary()

    # ----- data --------------------------------------------------------- #
    def dna(self) -> dict:
        sj = self._profile.style_json or {}
        perf = sj.get("performance", {})
        return {
            "username": self._player.username,
            "display_name": self._player.display_name,
            "headline": self._profile.headline(),
            "breakdown": sj.get("breakdown", {}),
            "rates": sj.get("rates", {}),
            "opening_preferences": self._profile.opening_preferences,
            "performance": perf,
            "total_games": perf.get("total_games", self._total_games),
        }
