"""Strongly-typed domain models shared across every layer.

These mirror the database tables one-to-one (PHASES 1-3) but are plain
dataclasses so services can pass them around without touching SQL. `id`/
`created_at` are optional because they are assigned by the database on insert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Player:
    username: str
    display_name: str
    source: str = "chess.com"
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class Game:
    player_id: int
    date: str
    color: str                 # 'white' | 'black'
    result: str                # 'win' | 'loss' | 'draw'
    opening: str
    eco: str
    time_control: str
    opponent_name: str
    opponent_rating: Optional[int]
    move_count: int
    pgn: str
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class PlayerMove:
    player_id: int
    game_id: int
    move_number: int
    fen: str                   # FEN of the position the move was made IN (pre-move)
    move_played: str           # SAN chosen from that position
    opening: str
    phase: str                 # OPENING | MIDDLEGAME | ENDGAME
    evaluation: int            # static eval after the move, White's perspective (cp)
    mover: str = "w"           # 'w'/'b' — convenience, derivable from fen turn
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class StyleProfile:
    """The player's style fingerprint — the heart of the clone.

    The five headline scores are 0-100. `opening_preferences` and `style_json`
    carry the richer breakdown (sub-metrics, per-opening stats) that the DNA
    page and the move scorer consume.
    """
    player_id: int
    aggression: int
    tactical: int
    risk: int
    king_safety: int
    endgame: int
    opening_preferences: dict = field(default_factory=dict)
    style_json: dict = field(default_factory=dict)
    id: Optional[int] = None
    updated_at: Optional[str] = None

    def headline(self) -> dict:
        """The compact fingerprint shown in the spec's example output."""
        return {
            "aggression": self.aggression,
            "tactical": self.tactical,
            "risk": self.risk,
            "kingSafety": self.king_safety,
            "endgame": self.endgame,
        }
