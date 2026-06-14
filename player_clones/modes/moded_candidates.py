"""ModedCandidateProvider — blunder injection at the candidate stage.

Wraps the existing `CandidateProvider` (which it does not reimplement) and
applies one mode knob before the style scorer sees the moves:

* **blunder injection** — with probability `blunder_rate`, the near-best moves
  are *removed*, forcing the selection into the "human blunder" band
  (`blunder_loss_range` centipawns worse than best). If the position offers no
  move in that band (everything is forced/equal), no blunder happens — exactly
  like a human who can't go wrong in a simple position.

The *accuracy floor* (eval window) lives in `PlayerCloneEngine.sanity_window_cp`
— one place, applied relative to whatever list this provider returns, so an
injected blunder band still works (the engine's window is band-relative).

Because filtering happens at the candidate stage, the style scorer still picks
the most Samay-like move *of whatever quality tier the mode allows* — the
personality layer is untouched.
"""

from __future__ import annotations

import random
from typing import Optional

from engine import State
from player_clones.clone_engine.candidate_provider import CandidateProvider, Candidate
from player_clones.modes.mode_config import ModeConfig


class ModedCandidateProvider:
    """Drop-in for `CandidateProvider` (same `top_moves` contract)."""

    def __init__(self, config: ModeConfig, rng: Optional[random.Random] = None,
                 base: Optional[CandidateProvider] = None):
        self.config = config
        self.rng = rng or random.Random()
        self.base = base or CandidateProvider(depth=config.depth,
                                              use_quiesce=config.quiesce)

    def top_moves(self, state: State, top_n: int = 20) -> list[Candidate]:
        cfg = self.config
        # fetch a little extra so injection still leaves a real choice
        cands = self.base.top_moves(state, max(top_n, 12))
        if not cands:
            return []
        best = cands[0].eval_cp

        # human blunder injection
        if cfg.blunder_rate > 0 and self.rng.random() < cfg.blunder_rate:
            lo, hi = cfg.blunder_loss_range
            blunders = [c for c in cands if lo <= best - c.eval_cp <= hi]
            if blunders:
                return blunders[:top_n]

        return cands[:top_n]
