"""Lightweight opening classifier for the post-game report (PHASE 8).

Reuses the opening corpus the app already ships in `knowledge.OPENING_LINES`
(plus the famous-game openings) rather than introducing a new ECO database.
Given the SAN move list of a game, return the name of the longest known opening
line that prefixes it.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _prefix_table() -> list[tuple[tuple, str]]:
    """Build (san_prefix_tuple, name) pairs sorted longest-first."""
    import knowledge
    table: list[tuple[tuple, str]] = []
    for name, moves in knowledge.OPENING_LINES:
        table.append((tuple(moves.split()), name))
    # famous games contribute their first moves as named openings too
    for game in getattr(knowledge, "FAMOUS_GAMES", []):
        toks = tuple(game["moves"].split()[:12])
        if toks:
            table.append((toks, game["name"]))
    table.sort(key=lambda t: len(t[0]), reverse=True)
    return table


def classify_opening(san_moves: list[str], min_match: int = 3) -> str:
    """Best-matching opening name for a game's SAN list, or 'Unknown'.

    Scores each known line by how many leading moves it shares with the game and
    returns the name with the longest agreement (>= `min_match` plies). This
    matches both short games (a prefix of a long theory line) and long games
    (that fully contain a short line).
    """
    if not san_moves:
        return "Unknown"
    seq = [s.rstrip("+#") for s in san_moves]
    best_name, best_len = "Unknown", 0
    for prefix, name in _prefix_table():
        match = 0
        for i in range(min(len(prefix), len(seq))):
            if prefix[i].rstrip("+#") == seq[i]:
                match += 1
            else:
                break
        if match > best_len:
            best_name, best_len = name, match
    return best_name if best_len >= min_match else "Unknown"
