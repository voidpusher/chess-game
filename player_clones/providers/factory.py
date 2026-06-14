"""create_player_clone — the one-call entry point (PHASE 5 + FUTURE REQUIREMENT).

    create_player_clone("samayraina")     # works offline from the bundled sample
    create_player_clone("magnuscarlsen")  # live-imports from Chess.com
    create_player_clone("hikaru")
    create_player_clone("any_chesscom_username")

No per-player code: the same bootstrap (ensure imported -> ensure analyzed ->
build provider) serves everyone. `source` controls where data comes from:

    "auto"   - use already-stored data; else the offline sample if available;
               else a live Chess.com import.  (default)
    "sample" - force the bundled offline sample (samayraina only).
    "live"   - force a live Chess.com import / refresh.
"""

from __future__ import annotations

import random
from typing import Optional

from player_clones.db import Database
from player_clones.models import Player
from player_clones.importer.player_importer import PlayerImporterService
from player_clones.importer.chesscom_client import ChessComClient, ChessComError
from player_clones.importer.sample_data import SampleChessComClient, SAMPLE_USERNAMES
from player_clones.style_analysis.style_analyzer import PlayerStyleAnalyzer
from player_clones.providers.player_clone_provider import PlayerCloneProvider

# Bound the first live import so building a clone is responsive; a full backfill
# is available via the CLI (`python -m player_clones.cli import <user> --full`).
_BOOTSTRAP_MAX_ARCHIVES = 24
_BOOTSTRAP_MAX_GAMES = 3000


def create_player_clone(username: str,
                        db: Optional[Database] = None,
                        source: str = "auto",
                        candidate_depth: int = 2,
                        rng: Optional[random.Random] = None) -> PlayerCloneProvider:
    username = username.lower()
    db = db or Database()

    player = _ensure_ingested(db, username, source)
    if db.styles.get(player.id) is None:
        PlayerStyleAnalyzer(db).analyze(player.id)
    profile = db.styles.get(player.id)

    return PlayerCloneProvider(db, player, profile,
                               candidate_depth=candidate_depth, rng=rng)


def refresh_player_clone(username: str, db: Optional[Database] = None,
                         full: bool = False) -> PlayerCloneProvider:
    """Re-sync from Chess.com and re-analyze, then return a fresh provider."""
    db = db or Database()
    importer = PlayerImporterService(db, client=ChessComClient())
    if full:
        importer.import_player(username)
    else:
        importer.sync_player(username)
    player = db.players.get_by_username(username)
    PlayerStyleAnalyzer(db).analyze(player.id)
    profile = db.styles.get(player.id)
    return PlayerCloneProvider(db, player, profile)


def import_all_samay(db: Optional[Database] = None):
    """Full, unlimited live import of Samay's entire Chess.com history.

    Unlike the bounded bootstrap (which caps archives/games for responsiveness),
    this scans every monthly archive with no game cap, then rebuilds the
    fingerprint. Returns the ImportSummary. Falls back to the bundled sample only
    if the network is unavailable.
    """
    db = db or Database()
    importer = PlayerImporterService(db, client=ChessComClient())
    try:
        summary = importer.import_player("samayraina",
                                         max_archives=None, max_games=None)
    except ChessComError:
        importer = PlayerImporterService(db, client=SampleChessComClient())
        summary = importer.import_player("samayraina")
    player = db.players.get_by_username("samayraina")
    if player:
        PlayerStyleAnalyzer(db).analyze(player.id)
    return summary


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #

def _ensure_ingested(db: Database, username: str, source: str) -> Player:
    existing = db.players.get_by_username(username)
    if existing and db.games.count(existing.id) > 0 and source != "live":
        return existing                      # already have data — reuse it

    if source == "sample":
        _import_sample(db, username)
    elif source == "live":
        _import_live(db, username)
    else:  # auto
        # Production behaviour: ALWAYS try a live Chess.com import first so the
        # clone reflects the player's real, current games. `_import_live` falls
        # back to the bundled offline sample on any network/user failure for the
        # usernames we ship one for (e.g. samayraina), keeping the call usable
        # offline and in CI.
        _import_live(db, username)

    player = db.players.get_by_username(username)
    if player is None or db.games.count(player.id) == 0:
        raise ChessComError(
            f"Could not build a clone for '{username}': no games available. "
            f"Check the username, or pass source='live' to import from Chess.com."
        )
    return player


def _import_sample(db: Database, username: str) -> None:
    if username not in SAMPLE_USERNAMES:
        raise ChessComError(
            f"No offline sample bundled for '{username}'. "
            f"Use source='live' to import from Chess.com."
        )
    PlayerImporterService(db, client=SampleChessComClient()).import_player(username)


def _import_live(db: Database, username: str) -> None:
    importer = PlayerImporterService(db, client=ChessComClient())
    try:
        importer.import_player(username,
                               max_archives=_BOOTSTRAP_MAX_ARCHIVES,
                               max_games=_BOOTSTRAP_MAX_GAMES)
    except ChessComError:
        # Network/user failure: fall back to the sample if we have one.
        if username in SAMPLE_USERNAMES:
            _import_sample(db, username)
        else:
            raise
