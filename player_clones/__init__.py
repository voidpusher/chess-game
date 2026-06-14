"""Player Clone Engine.

A self-contained system that lets a user play against a *style clone* of any
real Chess.com player. The clone does not try to play the strongest move — it
tries to play the move the real player is most likely to play.

The architecture is deliberately username-agnostic. The same pipeline builds a
clone for any public Chess.com account:

    from player_clones import create_player_clone

    samay = create_player_clone("samayraina")
    magnus = create_player_clone("magnuscarlsen")
    move = samay.choose_move(state)        # a `engine.Move`

Pipeline (per PRODUCT VISION / PHASES 1-5):

    Chess.com archives  ->  PlayerImporterService   (PHASE 1)
            |
            v
    PGNs in SQLite      ->  PgnParser / move DB      (PHASE 2)
            |
            v
    player_moves        ->  PlayerStyleAnalyzer      (PHASE 3)
            |
            v
    style fingerprint   ->  PlayerCloneEngine        (PHASE 4)
            |                + MoveStyleScorer
            v
    Provider            ->  create_player_clone(...)  (PHASE 5)

Nothing in here reimplements board logic, move generation or search — it reuses
the existing `engine` module. It only *re-ranks* engine output by player style.
"""

__all__ = ["create_player_clone", "SamayCloneProvider"]


def __getattr__(name):
    # Lazy re-exports so `import player_clones` stays cheap and tolerant of
    # partial builds (the GUI/engine chain is only pulled when actually used).
    if name == "create_player_clone":
        from player_clones.providers.factory import create_player_clone
        return create_player_clone
    if name == "SamayCloneProvider":
        from player_clones.providers.samay_provider import SamayCloneProvider
        return SamayCloneProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
