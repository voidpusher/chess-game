"""ModeConfig — a mode is a parameter set, nothing more.

Every knob below maps onto something the existing clone stack already supports:

    depth / quiesce        -> CandidateProvider (move quality ceiling)
    top_n / temperature    -> PlayerCloneEngine (selection randomness)
    repertoire_fidelity    -> PlayerCloneEngine (how faithfully he follows his
                              own historical moves)
    eval_window_cp         -> ModedCandidateProvider (accuracy floor: only moves
                              within X centipawns of the best are considered)
    blunder_rate / range   -> ModedCandidateProvider (human blunder injection)
    style_scale            -> scorer profile multipliers (personality emphasis;
                              empty = the authentic fingerprint)

REAL deliberately equals the engine defaults exactly — selecting it produces the
same engine the clone has always used, with zero artificial adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ModeConfig:
    key: str
    title: str
    description: str
    strength: str                       # human-readable estimate for the UI

    # candidate quality (engine accuracy)
    depth: int = 2
    quiesce: bool = True

    # selection behaviour (PlayerCloneEngine params; defaults == engine defaults)
    top_n: int = 20
    temperature: float = 0.35
    repertoire_fidelity: float = 0.9

    # accuracy controls (ModedCandidateProvider; None/0 = off)
    eval_window_cp: Optional[int] = None
    blunder_rate: float = 0.0
    blunder_loss_range: tuple = (120, 700)   # a "human" blunder, in centipawns

    # personality emphasis: axis -> multiplier applied to the style profile the
    # scorer sees (clamped to 0-100). Empty dict = authentic fingerprint.
    style_scale: dict = field(default_factory=dict)


CASUAL = ModeConfig(
    key="casual",
    title="Casual Samay",
    description=("Stream Samay having fun — impulsive, sacrifice-happy, plays "
                 "for the highlight reel and sometimes ignores the best move."),
    strength="~800–1200",
    depth=1, quiesce=False,              # shallow eval: misses tactics like a casual game
    top_n=10,                            # choose from top 10 style-ranked moves
    temperature=0.85,                    # lots of randomness
    repertoire_fidelity=0.7,             # often wanders out of his own book
    blunder_rate=0.28,                   # occasionally just lets one go
    style_scale={"aggression": 1.35, "risk": 1.5, "tactical": 1.1},
)

REAL = ModeConfig(
    key="real",
    title="Real Samay",
    description=("Authentic Samay clone — his historical openings, tendencies "
                 "and style fingerprint, exactly as the data shows."),
    strength="Historical (~his rapid level)",
    # == the clone engine's own defaults: depth-3 candidates with the standard
    # 130cp sanity floor. Style picks the most Samay-like move among sound
    # moves — he plays with flair, but he does not hang pieces for vibes.
    depth=3, quiesce=True,
    eval_window_cp=130,
)

PEAK = ModeConfig(
    key="peak",
    title="Peak Samay",
    description=("Locked-in Samay — the same personality and aggression, but "
                 "every move comes from the engine's best candidates: fewer "
                 "blunders, sharper conversion, cleaner endgames."),
    strength="His ceiling (engine-checked)",
    depth=3, quiesce=True,               # deepest search this app runs
    top_n=8,
    temperature=0.08,                    # near-deterministic
    repertoire_fidelity=0.95,
    eval_window_cp=60,                   # only near-best moves are considered
    # style_scale empty: aggression profile unchanged, per spec
)

MODE_PRESETS = {m.key: m for m in (CASUAL, REAL, PEAK)}


def adaptive_config(user_rating: int) -> ModeConfig:
    """ADAPTIVE — "Samay at your level".

    Personality knobs (style_scale, openings, repertoire) stay authentic; only
    accuracy-related knobs move with the user's rating. The bot targets roughly
    `user_rating + 75` so it is a slight challenge at every level.
    """
    r = max(400, min(2400, int(user_rating)))
    target = r + 75

    if r < 800:
        depth, quiesce, window, blunder, temp = 1, False, None, 0.35, 0.70
    elif r < 1100:
        depth, quiesce, window, blunder, temp = 1, False, 500, 0.22, 0.55
    elif r < 1400:
        depth, quiesce, window, blunder, temp = 2, True, 300, 0.12, 0.40
    elif r < 1700:
        depth, quiesce, window, blunder, temp = 2, True, 180, 0.06, 0.28
    elif r < 2000:
        depth, quiesce, window, blunder, temp = 3, True, 120, 0.03, 0.16
    else:
        depth, quiesce, window, blunder, temp = 3, True, 70, 0.01, 0.08

    return ModeConfig(
        key="adaptive",
        title="Adaptive Samay",
        description=("Samay matched to your level — same openings, aggression "
                     "and risk appetite, accuracy tuned to give you a fair, "
                     "slightly challenging game."),
        strength=f"~{target}–{target + 100} (you: {r})",
        depth=depth, quiesce=quiesce,
        top_n=14, temperature=temp, repertoire_fidelity=0.9,
        eval_window_cp=window, blunder_rate=blunder,
    )
