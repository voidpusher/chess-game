"""CandidateProvider — the "top-N engine moves" stage (PHASE 4).

The spec's pipeline starts from "Top 20 Stockfish moves". This project uses its
own alpha-beta engine instead of Stockfish (per the chosen architecture), so we
produce the same thing — a shortlist of the strongest legal moves with their
evaluations — by scoring every legal move with the existing `engine.negamax`.

This is effectively a multi-PV: it bounds the clone to *reasonable* moves so a
style-driven choice never hangs a piece for nothing, while still leaving room
for the human-like / sacrificial choices the scorer prefers.
"""

from __future__ import annotations

from dataclasses import dataclass

import engine
from engine import (
    State, Move, legal_moves, make_move, unmake_move, order_moves, negamax, INF,
)


@dataclass
class Candidate:
    move: Move
    san: str
    eval_cp: int          # evaluation from the moving side's perspective (cp)

    @property
    def uci(self) -> str:
        return self.move.uci()


class CandidateProvider:
    """Ranks legal moves by engine evaluation and returns the best `top_n`."""

    def __init__(self, depth: int = 2, use_quiesce: bool = True):
        # depth 2 + quiescence ≈ the existing "medium/hard" strength: strong
        # enough to avoid blunders, cheap enough to stay responsive in the GUI.
        self.depth = depth
        self.use_quiesce = use_quiesce

    def top_moves(self, state: State, top_n: int = 20) -> list[Candidate]:
        moves = legal_moves(state)
        if not moves:
            return []
        order_moves(state, moves)
        scored: list[Candidate] = []
        for m in moves:
            san = engine.to_san(state, m)
            undo = make_move(state, m)
            # Full window: we need exact, comparable scores for every candidate,
            # not the alpha-beta bound shortcuts `search_best_move` can take.
            score = -negamax(state, self.depth - 1, -INF, INF, 1, self.use_quiesce)
            unmake_move(state, m, undo)
            scored.append(Candidate(move=m, san=san, eval_cp=int(score)))
        scored.sort(key=lambda c: c.eval_cp, reverse=True)
        return scored[:top_n]
