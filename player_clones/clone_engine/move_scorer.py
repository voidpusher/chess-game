"""MoveStyleScorer — how "player-like" is a candidate move? (PHASE 4)

Given a candidate move and the player's `StyleProfile`, produce a `style_score`
(higher = more characteristic of the player) plus a breakdown of which style
axes drove it. The scorer is deliberately transparent: each axis of the
fingerprint gates a set of move features, so a high-aggression profile rewards
checks/captures/king-attacks, a high-risk profile rewards sacrifices, a
high-king-safety profile rewards castling and discourages king wandering, etc.

The score is unitless; only the *ordering* it induces over candidates matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine import State, Move, VAL
from player_clones import fen as fenutil
from player_clones.models import StyleProfile


@dataclass
class MoveScore:
    san: str
    style_score: float
    contributions: dict = field(default_factory=dict)
    in_repertoire: bool = False
    repertoire_weight: int = 0


# How strongly an exact-repertoire match outweighs pure style. A move the player
# has actually played in this position is the single best "play like them"
# signal, so it dominates — but the clone engine usually short-circuits to the
# repertoire before scoring at all; this only matters when blending.
_REPERTOIRE_BONUS = 6.0
_MATE_BONUS = 100.0          # everyone plays a forced mate


class MoveStyleScorer:
    """Scores candidate moves by similarity to a player's style fingerprint."""

    def __init__(self, profile: StyleProfile):
        self.profile = profile
        # axis weights normalised to 0..1
        self.agg = profile.aggression / 100.0
        self.tac = profile.tactical / 100.0
        self.risk = profile.risk / 100.0
        self.ks = profile.king_safety / 100.0
        self.eg = profile.endgame / 100.0
        self._pref_openings = self._collect_pref_openings(profile)

    @staticmethod
    def _collect_pref_openings(profile: StyleProfile) -> set[str]:
        names = set()
        prefs = profile.opening_preferences or {}
        for color in ("white", "black"):
            for entry in prefs.get(color, [])[:6]:
                if entry.get("opening"):
                    names.add(entry["opening"])
        return names

    def score(self, state: State, move: Move,
              repertoire_weight: int = 0,
              phase: str | None = None) -> MoveScore:
        f = fenutil.extract_features(state, move)
        if phase is None:
            phase = fenutil.classify_phase(state, 1)
        c: dict[str, float] = {}

        # --- aggression-gated features ------------------------------------ #
        if f.is_check:
            c["check"] = (0.6 * self.agg + 0.4 * self.tac)
        if f.is_capture:
            c["capture"] = 0.45 * self.agg * min(1.0, f.captured_value / VAL["Q"]) \
                + 0.15 * self.agg
        if f.attacks_king_zone:
            c["king_attack"] = 0.7 * self.agg
        if f.advances_into_enemy:
            c["advance"] = 0.3 * self.agg
        if f.central:
            c["central"] = 0.25 * self.agg

        # --- tactical-gated features -------------------------------------- #
        if f.creates_fork:
            c["fork"] = 0.9 * self.tac
        if f.gives_mate:
            c["mate"] = _MATE_BONUS
        if f.is_promotion:
            c["promotion"] = 0.5 * self.tac + 0.2

        # --- risk-gated features ------------------------------------------ #
        if f.is_sacrifice:
            # A risk-taker is *rewarded* for sacrifices; a safe player is
            # penalised for them. Centre the signal on risk so low-risk clones
            # actively avoid hanging material.
            c["sacrifice"] = 1.3 * self.risk - 0.8 * (1.0 - self.risk)

        # --- king-safety-gated features ----------------------------------- #
        if f.is_castle:
            c["castle"] = 0.9 * self.ks
        if f.king_move:
            # safe players dislike walking the king; risk-takers tolerate it
            c["king_walk"] = -0.6 * self.ks + 0.25 * self.risk
        if f.develops_piece and phase == fenutil.OPENING:
            c["development"] = 0.3

        # --- opening preference / repertoire ------------------------------ #
        if repertoire_weight > 0:
            c["repertoire"] = _REPERTOIRE_BONUS

        total = sum(c.values())
        return MoveScore(san=f.san, style_score=total, contributions=c,
                         in_repertoire=repertoire_weight > 0,
                         repertoire_weight=repertoire_weight)
