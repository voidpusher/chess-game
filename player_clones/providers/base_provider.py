"""CloneProvider — the abstract contract every clone fulfils (PHASE 5).

The GUI and post-game report depend on this interface, not on concrete clones,
so a new player clone is added without touching gameplay code (Open/Closed +
Dependency Inversion). The interface is intentionally tiny: pick a move, expose
identity, expose the style data, reset between games.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from engine import State, Move
from player_clones.clone_engine.clone_engine import CloneDecision
from player_clones.models import StyleProfile


class CloneProvider(ABC):
    @property
    @abstractmethod
    def username(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @property
    @abstractmethod
    def profile(self) -> StyleProfile: ...

    @abstractmethod
    def choose_move(self, state: State) -> Optional[Move]:
        """Return the move the clone would play in `state` (or None if no move)."""

    @abstractmethod
    def decide(self, state: State) -> CloneDecision:
        """Like :meth:`choose_move` but with the full decision record."""

    @abstractmethod
    def reset(self) -> None:
        """Clear per-game state (influence tracking) before a new game."""

    @abstractmethod
    def dna(self) -> dict:
        """Everything the DNA page / post-game report needs to render."""
