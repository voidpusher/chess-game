"""PGN parsing (PHASE 2).

Splits raw PGN into headers + movetext, tokenises SAN, and replays games through
the existing `engine` to emit per-move `PlayerMove` records (FEN, phase, eval).
"""

from player_clones.pgn_parser.pgn_parser import (
    PgnParser, ParsedGame, split_pgn, tokenize_movetext, game_metadata,
)

__all__ = [
    "PgnParser", "ParsedGame", "split_pgn", "tokenize_movetext", "game_metadata",
]
