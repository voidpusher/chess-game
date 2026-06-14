"""SamayCloneProvider — the first concrete clone (PHASE 5).

Per the spec this is built automatically from ``username = "samayraina"``. It is
a thin convenience over the generic factory, proving the architecture needs no
per-player code: Magnus, Hikaru, GothamChess or any public account are one
`create_player_clone(username)` call away.
"""

from __future__ import annotations

import random
from typing import Optional

from player_clones.db import Database
from player_clones.providers.player_clone_provider import PlayerCloneProvider
from player_clones.providers.factory import create_player_clone

SAMAY_USERNAME = "samayraina"


class SamayCloneProvider(PlayerCloneProvider):
    """A `PlayerCloneProvider` pre-bound to Samay Raina's Chess.com account.

    Use the classmethod :meth:`build` to construct one (it runs the
    import/analyze bootstrap and returns a fully-wired provider).
    """

    @classmethod
    def build(cls, db: Optional[Database] = None, source: str = "auto",
              candidate_depth: int = 2,
              rng: Optional[random.Random] = None) -> "PlayerCloneProvider":
        # Delegate to the factory; it already returns a PlayerCloneProvider with
        # Samay's repertoire + fingerprint wired in.
        return create_player_clone(SAMAY_USERNAME, db=db, source=source,
                                   candidate_depth=candidate_depth, rng=rng)
