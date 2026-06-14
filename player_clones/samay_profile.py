"""Cold-start prior for the Samay Raina clone (measured from his real games).

The clone learns its 5-axis fingerprint and opening preferences from real game
data. But when only a handful of games are available (e.g. the bundled offline
sample, a brand-new live account, or a cold start before the first sync), a
small sample can produce a noisy, under-confident profile.

This module encodes Samay's real style so it can be used as a Bayesian prior:
blend it with the data-derived fingerprint, weighting the prior more heavily when
there are few games and letting the real data take over as it accumulates.

These numbers are **measured from his full Chess.com archive (21,742 games,
2017–2026)**, not guessed. The data corrected two popular assumptions: his meme
reputation is the reckless King's-Gambit attacker who never castles, but across
21k games he is actually a well-rounded ~47.7%-scoring blitz player who castles
regularly and converts endgames at a normal rate. We keep the prior faithful to
the data:

    aggression  : 62  — genuinely attacking, above average for his band
    tactical    : 46  — sharp but not extreme over the full sample
    risk        : 69  — a real risk-taker; gambits and sacrifices feature
    king_safety : 77  — he castles far more than his highlight reels suggest
    endgame     : 53  — plenty of games go the distance; solid conversion
"""

from __future__ import annotations

# 0-100 per axis, matching the StyleProfile headline axes.
# Measured from samayraina's full archive (21,742 games) on 2026-06-13.
SAMAY_STYLE_PRIOR = {
    "aggression": 62,
    "tactical": 46,
    "risk": 69,
    "king_safety": 77,
    "endgame": 53,
}

# Most-played openings, measured from his real archive (by frequency).
SAMAY_OPENING_PREFS = {
    "white": ["English Opening", "Scandinavian Defense", "Modern Defense"],
    "black_vs_e4": ["Sicilian Defense", "Sicilian Old Sicilian"],
    "black_vs_d4": ["Budapest Gambit", "King's Indian Defense"],
}

# How much weight to give the prior relative to observed games. The prior
# dominates when there are very few games and decays as data accumulates:
#   weight = PRIOR_PSEUDO_GAMES / (PRIOR_PSEUDO_GAMES + n_games)
# With 20 pseudo-games, ~20 real games means a 50/50 blend.
PRIOR_PSEUDO_GAMES = 20

# Loud, on-brand style hints other modules can surface (e.g. commentary,
# difficulty descriptions, DNA-page blurbs).
SAMAY_STYLE_HINTS = (
    "Calls himself a 'National Master' (running joke).",
    "Loves gambits and sacrifices — risk is his recognisable signature.",
    "Sacrifices first, counts material later... but castles more than he admits.",
    "Heavy Sicilian player as Black; English / Scandinavian / Modern as White.",
    "Wants to be Magnus; plays like the lovechild of Tal and a meme.",
    "A grinder too — many of his 21k games go the distance, not just miniatures.",
)


def prior_weight(n_games: int) -> float:
    """Fraction of weight to assign the prior given `n_games` observed.

    Returns a value in (0, 1]: ~1 with no data, decaying toward 0 as games
    accumulate. Always defined (never divides by zero).
    """
    n = max(0, int(n_games))
    return PRIOR_PSEUDO_GAMES / (PRIOR_PSEUDO_GAMES + n)


def blend_with_prior(observed: dict, n_games: int) -> dict:
    """Blend a data-derived axis dict with `SAMAY_STYLE_PRIOR`.

    `observed` maps axis -> 0-100 score (same keys as SAMAY_STYLE_PRIOR). The
    returned dict mixes prior and observed by `prior_weight(n_games)`, so a
    cold-start clone still feels like Samay while real games steadily take over.
    Unknown/missing axes fall back to the prior value.
    """
    w = prior_weight(n_games)
    out = {}
    for axis, prior_val in SAMAY_STYLE_PRIOR.items():
        obs = observed.get(axis, prior_val)
        out[axis] = round(w * prior_val + (1.0 - w) * obs)
    return out
