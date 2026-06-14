"""Pure scoring/aggregation helpers for the style analyzer (PHASE 3).

Everything here is deterministic and side-effect-free: given aggregated move
features and game rows, produce the 0-100 axis scores, opening preferences and
performance breakdowns. Keeping the maths separate from DB/replay concerns makes
the formulas easy to read, test and tune.

The axis formulas are transparent weighted blends of intuitive *rates* (how
often the player checks, captures, sacrifices, castles, ...). Calibration
constants (`lo`/`hi` bounds) encode "this rate is unremarkable" vs "this rate is
maximal" from practical chess experience. They are the one place to tune if a
clone should feel more/less aggressive.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


def scale(value: float, lo: float, hi: float) -> float:
    """Linearly map `value` in [lo, hi] to [0, 100], clamped."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100.0))


@dataclass
class FeatureAggregate:
    """Running tallies over a player's moves and games."""
    n_moves: int = 0
    n_games: int = 0
    checks: int = 0
    captures: int = 0
    king_zone: int = 0
    advances: int = 0
    central: int = 0
    sacrifices: int = 0
    forks: int = 0
    mates: int = 0
    promotions: int = 0
    developing: int = 0
    # opening-phase specials
    opening_sacrifices: int = 0     # gambit signal
    opening_king_moves: int = 0     # king exposure signal
    # per-game flags
    games_castled: int = 0
    games_reached_endgame: int = 0
    games_won_endgame: int = 0

    def rate(self, field_name: str) -> float:
        n = self.n_moves or 1
        return getattr(self, field_name) / n


# --------------------------------------------------------------------------- #
# Axis scores
# --------------------------------------------------------------------------- #

def aggression_score(agg: FeatureAggregate) -> tuple[int, dict]:
    checks = scale(agg.rate("checks"), 0.0, 0.18)
    captures = scale(agg.rate("captures"), 0.18, 0.5)
    kingzone = scale(agg.rate("king_zone"), 0.0, 0.14)
    advances = scale(agg.rate("advances"), 0.12, 0.5)
    sacs = scale(agg.rate("sacrifices"), 0.0, 0.07)
    score = 0.25 * checks + 0.20 * captures + 0.25 * kingzone + \
        0.15 * advances + 0.15 * sacs
    parts = {"checks": round(checks), "captures": round(captures),
             "king_zone": round(kingzone), "advances": round(advances),
             "sacrifices": round(sacs)}
    return round(score), parts


def tactical_score(agg: FeatureAggregate) -> tuple[int, dict]:
    forks = scale(agg.rate("forks"), 0.0, 0.09)
    mates = scale(agg.mates / (agg.n_games or 1), 0.0, 0.5)
    checks = scale(agg.rate("checks"), 0.0, 0.22)
    sacs = scale(agg.rate("sacrifices"), 0.0, 0.07)
    promos = scale(agg.rate("promotions"), 0.0, 0.05)
    score = 0.38 * forks + 0.20 * mates + 0.20 * checks + \
        0.14 * sacs + 0.08 * promos
    parts = {"forks": round(forks), "mates": round(mates),
             "checks": round(checks), "sacrifices": round(sacs),
             "promotions": round(promos)}
    return round(score), parts


def risk_score(agg: FeatureAggregate) -> tuple[int, dict]:
    sacs = scale(agg.rate("sacrifices"), 0.0, 0.05)
    gambits = scale(agg.opening_sacrifices / (agg.n_games or 1), 0.0, 0.6)
    king_walk = scale(agg.opening_king_moves / (agg.n_games or 1), 0.0, 0.8)
    score = 0.45 * sacs + 0.35 * gambits + 0.20 * king_walk
    parts = {"sacrifices": round(sacs), "gambits": round(gambits),
             "king_walks": round(king_walk)}
    return round(score), parts


def king_safety_score(agg: FeatureAggregate) -> tuple[int, dict]:
    """Higher = safer king. Castling habit raises it; early king wandering lowers it."""
    castle_rate = agg.games_castled / (agg.n_games or 1)
    castled = scale(castle_rate, 0.35, 0.95)
    exposure = scale(agg.opening_king_moves / (agg.n_games or 1), 0.0, 0.8)
    score = 0.75 * castled + 0.25 * (100.0 - exposure)
    parts = {"castling": round(castled), "exposure_penalty": round(exposure)}
    return round(score), parts


def endgame_score(agg: FeatureAggregate) -> tuple[int, dict]:
    reached = agg.games_reached_endgame
    conversion = (agg.games_won_endgame / reached) if reached else 0.0
    conv = scale(conversion, 0.0, 1.0)
    reach = scale(reached / (agg.n_games or 1), 0.0, 0.5)
    # A player who reaches few endgames (decisive early attacker) scores lower
    # here by design — that *is* their endgame fingerprint.
    score = 0.7 * conv + 0.3 * reach
    parts = {"conversion": round(conv), "reach": round(reach),
             "endgames": reached, "won": agg.games_won_endgame}
    return round(score), parts


# --------------------------------------------------------------------------- #
# Opening preferences & performance breakdowns (for the clone + DNA page)
# --------------------------------------------------------------------------- #

def _winrate(rows) -> float:
    if not rows:
        return 0.0
    wins = sum(1 for r in rows if r["result"] == "win")
    return round(100.0 * wins / len(rows), 1)


def opening_preferences(games) -> dict:
    """Most-played openings per colour with counts and win rates.

    `games` is a list of objects with `.color`, `.opening`, `.result`.
    Returns {"white": [...], "black": [...]} sorted by frequency.
    """
    out = {}
    for color in ("white", "black"):
        buckets = defaultdict(list)
        for g in games:
            if g.color == color and g.opening:
                buckets[g.opening].append({"result": g.result})
        ranked = sorted(
            ({"opening": name,
              "count": len(rows),
              "win_rate": _winrate(rows)} for name, rows in buckets.items()),
            key=lambda d: d["count"], reverse=True,
        )
        out[color] = ranked
    return out


def performance_breakdowns(games) -> dict:
    """Aggregate stats the DNA page charts: by colour, by time control, by opening."""
    def tally(rows):
        return {
            "games": len(rows),
            "wins": sum(1 for r in rows if r.result == "win"),
            "losses": sum(1 for r in rows if r.result == "loss"),
            "draws": sum(1 for r in rows if r.result == "draw"),
            "win_rate": round(100.0 * sum(1 for r in rows if r.result == "win")
                              / len(rows), 1) if rows else 0.0,
        }

    by_color = {c: tally([g for g in games if g.color == c])
                for c in ("white", "black")}

    tc_buckets = defaultdict(list)
    for g in games:
        tc_buckets[_time_class(g.time_control)].append(g)
    by_time = {tc: tally(rows) for tc, rows in tc_buckets.items()}

    op_buckets = defaultdict(list)
    for g in games:
        if g.opening:
            op_buckets[g.opening].append(g)
    by_opening = sorted(
        ({"opening": name, **tally(rows)} for name, rows in op_buckets.items()),
        key=lambda d: d["games"], reverse=True,
    )

    return {
        "by_color": by_color,
        "by_time_control": by_time,
        "by_opening": by_opening,
        "total_games": len(games),
        "overall": tally(games),
    }


def _time_class(time_control: str) -> str:
    """Bucket a TimeControl string into bullet/blitz/rapid/classical/daily."""
    if not time_control:
        return "unknown"
    if "/" in time_control:           # daily games look like "1/86400"
        return "daily"
    base = time_control.split("+")[0]
    try:
        seconds = int(base)
    except ValueError:
        return "unknown"
    if seconds < 180:
        return "bullet"
    if seconds < 600:
        return "blitz"
    if seconds < 1800:
        return "rapid"
    return "classical"
