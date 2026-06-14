"""The clone engine (PHASE 4).

    Current position
        -> CandidateProvider  (top-N engine moves; the "Stockfish" stage)
        -> MoveStyleScorer    (rank candidates by player-likeness)
        -> PlayerCloneEngine  (pick the most player-like move)

No ML, no neural nets — just the existing search for *legality/strength bounds*
and a transparent style score for *selection*. When the live position exactly
matches one the real player has been in, the engine simply mimics what they
actually played.
"""

from player_clones.clone_engine.candidate_provider import (
    CandidateProvider, Candidate,
)
from player_clones.clone_engine.move_scorer import MoveStyleScorer, MoveScore
from player_clones.clone_engine.clone_engine import (
    PlayerCloneEngine, CloneDecision,
)

__all__ = [
    "CandidateProvider", "Candidate",
    "MoveStyleScorer", "MoveScore",
    "PlayerCloneEngine", "CloneDecision",
]
