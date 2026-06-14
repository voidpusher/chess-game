"""ModedCloneProvider — a mode applied to an existing clone, by composition.

Takes an already-built `PlayerCloneProvider` (with its 500k-position repertoire
snapshot and real style profile) and a `ModeConfig`, and presents the same
`CloneProvider` interface with the mode's selection behaviour. Construction is
effectively free — the expensive assets (repertoire, profile, DB) are shared
with the base, never rebuilt.

What a mode may change (and nothing else, per spec):
  * move selection strategy   (top_n / eval window / repertoire fidelity)
  * randomness                (temperature, blunder injection)
  * accuracy                  (candidate depth/quiescence, eval window)
  * risk-profile weights      (style_scale multipliers on the scorer's profile)

`dna()` always reports the *authentic* profile — the DNA page shows the real
player, while `profile` returns the in-play (possibly emphasised) fingerprint
the post-game report should describe.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Optional

from engine import State, Move
from player_clones.models import StyleProfile
from player_clones.clone_engine.clone_engine import PlayerCloneEngine, CloneDecision
from player_clones.clone_engine.move_scorer import MoveStyleScorer
from player_clones.providers.base_provider import CloneProvider
from player_clones.providers.player_clone_provider import PlayerCloneProvider
from player_clones.modes.mode_config import ModeConfig
from player_clones.modes.moded_candidates import ModedCandidateProvider


def scaled_profile(profile: StyleProfile, style_scale: dict) -> StyleProfile:
    """The profile the scorer sees, with mode multipliers applied (clamped)."""
    if not style_scale:
        return profile

    def s(axis: str, value: int) -> int:
        return max(0, min(100, round(value * style_scale.get(axis, 1.0))))

    return replace(
        profile,
        aggression=s("aggression", profile.aggression),
        tactical=s("tactical", profile.tactical),
        risk=s("risk", profile.risk),
        king_safety=s("king_safety", profile.king_safety),
        endgame=s("endgame", profile.endgame),
    )


class ModedCloneProvider(CloneProvider):
    def __init__(self, base: PlayerCloneProvider, config: ModeConfig,
                 rng: Optional[random.Random] = None):
        rng = rng or random.Random()
        self._base = base
        self.mode = config
        self._profile = scaled_profile(base.profile, config.style_scale)
        self._engine = PlayerCloneEngine(
            self._profile,
            # share the base provider's in-memory repertoire snapshot
            repertoire_lookup=lambda key: base._repertoire.get(key, []),
            scorer=MoveStyleScorer(self._profile),
            candidate_provider=ModedCandidateProvider(config, rng=rng),
            top_n=config.top_n,
            temperature=config.temperature,
            repertoire_fidelity=config.repertoire_fidelity,
            # the mode's eval window IS the engine's sanity floor (None = wild)
            sanity_window_cp=config.eval_window_cp,
            rng=rng,
        )

    # ----- identity ------------------------------------------------------ #
    @property
    def username(self) -> str:
        return self._base.username

    @property
    def display_name(self) -> str:
        return self.mode.title                      # "Casual Samay", "Peak Samay", ...

    @property
    def profile(self) -> StyleProfile:
        return self._profile                        # the fingerprint in play

    # ----- gameplay ------------------------------------------------------ #
    def choose_move(self, state: State) -> Optional[Move]:
        return self._engine.choose_move(state)

    def decide(self, state: State) -> CloneDecision:
        return self._engine.decide(state)

    def reset(self) -> None:
        self._engine.influence.clear()

    def influence_summary(self):
        return self._engine.influence_summary()

    # ----- data ----------------------------------------------------------- #
    def dna(self) -> dict:
        return self._base.dna()                     # DNA page = the real player
