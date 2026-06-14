"""PlayerCloneEngine — choose the most player-like move (PHASE 4).

Selection has two tiers:

1. **Repertoire mimicry.** If the live position is one the real player has
   actually been in (looked up by position key over their `player_moves`), play
   what they played — weighted by how often. This is the strongest possible
   "play like them" signal and makes the clone reproduce real opening lines and
   pet moves verbatim.

2. **Style ranking.** Otherwise take the top-N engine candidates (bounding move
   quality) and pick the one the `MoveStyleScorer` rates most characteristic of
   the player, with a little temperature so the clone is not robotically
   deterministic.

The engine depends on a `repertoire_lookup` callable, not on the database
directly, so it stays decoupled and trivially testable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

import engine
from engine import State, Move, legal_moves
from player_clones import fen as fenutil
from player_clones.db import position_key
from player_clones.models import StyleProfile
from player_clones.clone_engine.candidate_provider import CandidateProvider, Candidate
from player_clones.clone_engine.move_scorer import MoveStyleScorer, MoveScore

# Signature: position_key(str) -> list of (san, times_played)
RepertoireLookup = Callable[[str], list[tuple[str, int]]]


@dataclass
class CloneDecision:
    move: Optional[Move]
    san: str
    source: str                       # 'repertoire' | 'style' | 'forced' | 'none'
    eval_cp: Optional[int] = None
    style_score: Optional[float] = None
    contributions: dict = field(default_factory=dict)
    ranked: list[MoveScore] = field(default_factory=list)


class PlayerCloneEngine:
    def __init__(self, profile: StyleProfile,
                 repertoire_lookup: Optional[RepertoireLookup] = None,
                 scorer: Optional[MoveStyleScorer] = None,
                 candidate_provider: Optional[CandidateProvider] = None,
                 top_n: int = 20,
                 temperature: float = 0.35,
                 repertoire_fidelity: float = 0.9,
                 sanity_window_cp: Optional[int] = 130,
                 rng: Optional[random.Random] = None):
        self.profile = profile
        self.repertoire_lookup = repertoire_lookup or (lambda key: [])
        self.scorer = scorer or MoveStyleScorer(profile)
        self.candidates = candidate_provider or CandidateProvider()
        self.top_n = top_n
        self.temperature = temperature          # 0 = always the top style move
        self.repertoire_fidelity = repertoire_fidelity  # P(use a known move)
        # Style picks the most player-like move *among sound moves*: only
        # candidates within this many centipawns of the best are style-ranked.
        # The real player plays stylishly but does not hang pieces for vibes —
        # None disables the floor (Casual mode wants the chaos).
        self.sanity_window_cp = sanity_window_cp
        self.rng = rng or random.Random()

        # accumulates which style features fired across a game (post-game report)
        self.influence: dict[str, float] = {}

    # ------------------------------------------------------------------ API #
    def choose_move(self, state: State) -> Optional[Move]:
        return self.decide(state).move

    def decide(self, state: State) -> CloneDecision:
        legal = legal_moves(state)
        if not legal:
            return CloneDecision(move=None, san="", source="none")
        if len(legal) == 1:
            san = engine.to_san(state, legal[0])
            return CloneDecision(move=legal[0], san=san, source="forced")

        rep_decision = self._try_repertoire(state, legal)
        if rep_decision is not None:
            self._record(rep_decision)
            return rep_decision

        style_decision = self._style_choice(state, legal)
        self._record(style_decision)
        return style_decision

    # -------------------------------------------------------------- tier 1 #
    def _try_repertoire(self, state: State,
                        legal: list[Move]) -> Optional[CloneDecision]:
        key = position_key(fenutil.state_to_fen(state))
        played = self.repertoire_lookup(key)
        if not played:
            return None
        # keep only moves that are legal here (defensive against bad data)
        legal_by_san = {engine.to_san(state, m): m for m in legal}
        options = [(legal_by_san[san], n) for san, n in played if san in legal_by_san]
        if not options:
            return None
        if self.rng.random() > self.repertoire_fidelity:
            return None                       # occasionally deviate, like a human
        moves, weights = zip(*options)
        move = self.rng.choices(moves, weights=weights)[0]
        return CloneDecision(move=move, san=engine.to_san(state, move),
                             source="repertoire",
                             contributions={"repertoire": 1.0})

    # -------------------------------------------------------------- tier 2 #
    def _style_choice(self, state: State, legal: list[Move]) -> CloneDecision:
        candidates = self.candidates.top_moves(state, self.top_n)
        if not candidates:                    # provider gave nothing — fall back
            move = legal[0]
            return CloneDecision(move=move, san=engine.to_san(state, move),
                                 source="style")

        # Sanity floor: style only chooses among moves the engine considers
        # sound (within the window of the best candidate). Relative to the list
        # received, so mode-level filters (e.g. blunder injection) still work.
        if self.sanity_window_cp is not None and len(candidates) > 1:
            best_eval = candidates[0].eval_cp
            sound = [c for c in candidates
                     if best_eval - c.eval_cp <= self.sanity_window_cp]
            if sound:
                candidates = sound

        move_number = state.halfmove // 2 + 1
        phase = fenutil.classify_phase(state, move_number)
        eval_by_uci = {c.uci: c.eval_cp for c in candidates}

        ranked: list[tuple[Candidate, MoveScore]] = []
        for cand in candidates:
            ms = self.scorer.score(state, cand.move, phase=phase)
            ranked.append((cand, ms))

        # sort by style score, tie-break by engine eval so we never prefer a
        # clearly worse move when style is a wash
        ranked.sort(key=lambda pair: (pair[1].style_score, pair[0].eval_cp),
                    reverse=True)

        chosen_cand, chosen_score = self._sample(ranked)
        return CloneDecision(
            move=chosen_cand.move, san=chosen_cand.san, source="style",
            eval_cp=eval_by_uci.get(chosen_cand.uci),
            style_score=chosen_score.style_score,
            contributions=chosen_score.contributions,
            ranked=[ms for _, ms in ranked],
        )

    def _sample(self, ranked):
        """Pick among the top style moves with a temperature (softmax-ish)."""
        if self.temperature <= 0 or len(ranked) == 1:
            return ranked[0]
        top_score = ranked[0][1].style_score
        # candidates within `temperature` of the best style score are eligible
        window = max(0.4, abs(top_score) * self.temperature + 0.4)
        pool = [(c, s) for c, s in ranked if top_score - s.style_score <= window]
        # weight by closeness to the best, plus engine eval as a gentle nudge
        weights = []
        for c, s in pool:
            closeness = 1.0 - (top_score - s.style_score) / (window + 1e-9)
            weights.append(max(0.05, closeness))
        return self.rng.choices(pool, weights=weights)[0]

    # ------------------------------------------------------------- tracking #
    def _record(self, decision: CloneDecision) -> None:
        for k, v in decision.contributions.items():
            self.influence[k] = self.influence.get(k, 0.0) + (v if v > 0 else 0.0)

    def influence_summary(self) -> list[tuple[str, float]]:
        """Style features that most shaped this game, strongest first."""
        return sorted(self.influence.items(), key=lambda kv: kv[1], reverse=True)
