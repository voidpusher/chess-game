"""Clone providers + factory (PHASE 5).

A *provider* is the public handle the rest of the app talks to: give it a board
position, get back a move played in the cloned player's style. `PlayerCloneProvider`
is fully generic — `create_player_clone("any_username")` works without code
changes. `SamayCloneProvider` is the first concrete clone.
"""

from player_clones.providers.base_provider import CloneProvider
from player_clones.providers.player_clone_provider import PlayerCloneProvider
from player_clones.providers.samay_provider import SamayCloneProvider
from player_clones.providers.factory import create_player_clone

__all__ = [
    "CloneProvider", "PlayerCloneProvider", "SamayCloneProvider",
    "create_player_clone",
]
