"""PlayerImporterService — fetch, store, and parse a player's games (PHASE 1+2).

Reusable for ANY public Chess.com username. The service depends on three
abstractions — a `Database`, a `ChessComSource`, and a `PgnParser` — none of
which it constructs itself, so the same code serves live imports, offline
samples, and tests (Dependency Inversion / Single Responsibility).

    importer = PlayerImporterService(db)
    summary = importer.import_player("samayraina")      # full history
    summary = importer.sync_player("samayraina")        # recent months only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from player_clones.db import Database
from player_clones.models import Player
from player_clones.importer.chesscom_client import (
    ChessComSource, ChessComClient, ChessComError,
)
from player_clones.pgn_parser.pgn_parser import PgnParser, game_metadata


@dataclass
class ImportSummary:
    username: str
    player_id: int
    archives_scanned: int
    games_total: int        # total games now stored for the player
    games_new: int          # games newly inserted this run
    moves_added: int        # player_moves rows newly written this run

    def __str__(self) -> str:
        return (f"{self.username}: +{self.games_new} new games "
                f"({self.games_total} total), +{self.moves_added} moves "
                f"from {self.archives_scanned} archive(s)")


class PlayerImporterService:
    def __init__(self, db: Database,
                 client: Optional[ChessComSource] = None,
                 parser: Optional[PgnParser] = None):
        self.db = db
        self.client = client or ChessComClient()
        self.parser = parser or PgnParser()

    # ------------------------------------------------------------------ API #
    def import_player(self, username: str,
                      max_archives: Optional[int] = None,
                      max_games: Optional[int] = None) -> ImportSummary:
        """Import a player's full public history (or a bounded slice).

        `max_archives` limits how many recent monthly archives to scan;
        `max_games` caps total games (useful for a fast first-run bootstrap).
        """
        return self._ingest(username, max_archives=max_archives,
                            max_games=max_games)

    def sync_player(self, username: str,
                    recent_archives: int = 2) -> ImportSummary:
        """Incrementally pull newly-played games.

        Scans only the most recent `recent_archives` months and relies on the
        unique (player, pgn) constraint to skip everything already stored, so it
        is cheap to run on a schedule. Pass ``recent_archives=None`` via
        `import_player` for a full backfill.
        """
        return self._ingest(username, max_archives=recent_archives,
                            max_games=None)

    # -------------------------------------------------------------- internal #
    def _ingest(self, username: str, max_archives: Optional[int],
                max_games: Optional[int]) -> ImportSummary:
        username = username.lower()

        profile = self.client.get_profile(username)
        display = profile.get("name") or profile.get("username") or username
        source = "chess.com" if not str(self.client.__class__.__name__).startswith(
            "Sample") else "chess.com (sample)"
        player = self.db.players.upsert(
            Player(username=username, display_name=display, source=source))

        archives = self.client.get_archives(username)
        if max_archives is not None:
            archives = archives[-max_archives:]      # most recent months

        collected = []
        for url in archives:
            for gj in self.client.get_games(url):
                if gj.get("rules", "chess") != "chess":
                    continue                          # skip variants (960, etc.)
                pgn = gj.get("pgn")
                if not pgn:
                    continue
                game = game_metadata(pgn, username, gj)
                game.player_id = player.id
                collected.append(game)
                if max_games is not None and len(collected) >= max_games:
                    break
            if max_games is not None and len(collected) >= max_games:
                break

        games_new = self.db.games.insert_many(collected)

        # Parse only games whose moves were never extracted (idempotent).
        moves_added = 0
        for game in self.db.games.without_moves(player.id):
            moves = self.parser.parse_moves(game)
            moves_added += self.db.moves.insert_many(moves)

        return ImportSummary(
            username=username, player_id=player.id,
            archives_scanned=len(archives),
            games_total=self.db.games.count(player.id),
            games_new=games_new, moves_added=moves_added,
        )
