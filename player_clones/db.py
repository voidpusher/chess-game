"""SQLite persistence layer — schema + repositories.

The spec defines four tables (players, games, player_moves, player_styles). We
implement exactly those columns, add the few indexes/constraints good
engineering requires for idempotent syncing (PHASE 1 "support future syncing"),
and expose small repository objects so no other module writes raw SQL.

SQLite is used because it ships with the Python standard library — zero new
runtime dependencies, consistent with the existing project (`requirements.txt`
intentionally lists none). The default database lives next to this package; pass
``":memory:"`` for tests.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Iterable, Optional

from player_clones.models import Player, Game, PlayerMove, StyleProfile

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "player_clones.db")

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'chess.com',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id        INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    date             TEXT,
    color            TEXT,
    result           TEXT,
    opening          TEXT,
    eco              TEXT,
    time_control     TEXT,
    opponent_name    TEXT,
    opponent_rating  INTEGER,
    move_count       INTEGER,
    pgn              TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A game is uniquely identified (for idempotent sync) by player + its PGN.
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_player_pgn ON games(player_id, pgn);

CREATE TABLE IF NOT EXISTS player_moves (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    game_id      INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    move_number  INTEGER NOT NULL,
    fen          TEXT NOT NULL,
    move_played  TEXT NOT NULL,
    opening      TEXT,
    phase        TEXT NOT NULL,
    evaluation   INTEGER NOT NULL DEFAULT 0,
    mover        TEXT NOT NULL DEFAULT 'w',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_moves_player ON player_moves(player_id);
CREATE INDEX IF NOT EXISTS idx_moves_game   ON player_moves(game_id);
-- Repertoire lookup: "what did this player play in this exact position?"
CREATE INDEX IF NOT EXISTS idx_moves_player_fen ON player_moves(player_id, fen);

CREATE TABLE IF NOT EXISTS player_styles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id           INTEGER NOT NULL UNIQUE REFERENCES players(id) ON DELETE CASCADE,
    aggression          INTEGER NOT NULL,
    tactical            INTEGER NOT NULL,
    risk                INTEGER NOT NULL,
    king_safety         INTEGER NOT NULL,
    endgame             INTEGER NOT NULL,
    opening_preferences TEXT NOT NULL DEFAULT '{}',
    style_json          TEXT NOT NULL DEFAULT '{}',
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    """Thin connection wrapper that owns the schema and hands out repositories."""

    def __init__(self, path: str = DEFAULT_DB_PATH):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        # check_same_thread=False: the GUI builds a provider on a worker thread
        # and may read style data from the main thread. Our access is serialized
        # (one AI move at a time) and the clone engine reads its repertoire from
        # an in-memory snapshot, so cross-thread connection use stays safe.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

        self.players = PlayerRepository(self.conn)
        self.games = GameRepository(self.conn)
        self.moves = MoveRepository(self.conn)
        self.styles = StyleRepository(self.conn)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #

class PlayerRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, player: Player) -> Player:
        cur = self.conn.execute(
            """INSERT INTO players (username, display_name, source)
               VALUES (?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET display_name = excluded.display_name
               RETURNING id, created_at""",
            (player.username.lower(), player.display_name, player.source),
        )
        row = cur.fetchone()
        self.conn.commit()
        player.id, player.created_at = row["id"], row["created_at"]
        return player

    def get_by_username(self, username: str) -> Optional[Player]:
        row = self.conn.execute(
            "SELECT * FROM players WHERE username = ?", (username.lower(),)
        ).fetchone()
        return _row_to_player(row) if row else None

    def get(self, player_id: int) -> Optional[Player]:
        row = self.conn.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        return _row_to_player(row) if row else None


class GameRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_many(self, games: Iterable[Game]) -> int:
        """Insert games, skipping any whose (player_id, pgn) already exist.

        Returns the number of *new* rows actually written — the count `sync`
        reports as 'new games'.
        """
        inserted = 0
        for g in games:
            cur = self.conn.execute(
                """INSERT OR IGNORE INTO games
                   (player_id, date, color, result, opening, eco, time_control,
                    opponent_name, opponent_rating, move_count, pgn)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (g.player_id, g.date, g.color, g.result, g.opening, g.eco,
                 g.time_control, g.opponent_name, g.opponent_rating,
                 g.move_count, g.pgn),
            )
            inserted += cur.rowcount
        self.conn.commit()
        return inserted

    def for_player(self, player_id: int) -> list[Game]:
        rows = self.conn.execute(
            "SELECT * FROM games WHERE player_id = ? ORDER BY date", (player_id,)
        ).fetchall()
        return [_row_to_game(r) for r in rows]

    def without_moves(self, player_id: int) -> list[Game]:
        """Games that have no `player_moves` yet — the parse work queue.

        Makes ingestion idempotent: importing or syncing only parses games whose
        moves were never extracted, so re-runs are cheap and safe.
        """
        rows = self.conn.execute(
            """SELECT g.* FROM games g
               LEFT JOIN player_moves m ON m.game_id = g.id
               WHERE g.player_id = ? AND m.id IS NULL
               GROUP BY g.id ORDER BY g.date""",
            (player_id,),
        ).fetchall()
        return [_row_to_game(r) for r in rows]

    def count(self, player_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM games WHERE player_id = ?", (player_id,)
        ).fetchone()["n"]


class MoveRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_many(self, moves: Iterable[PlayerMove]) -> int:
        rows = [
            (m.player_id, m.game_id, m.move_number, m.fen, m.move_played,
             m.opening, m.phase, m.evaluation, m.mover)
            for m in moves
        ]
        self.conn.executemany(
            """INSERT INTO player_moves
               (player_id, game_id, move_number, fen, move_played, opening,
                phase, evaluation, mover)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def delete_for_game(self, game_id: int) -> None:
        self.conn.execute("DELETE FROM player_moves WHERE game_id = ?", (game_id,))
        self.conn.commit()

    def for_player(self, player_id: int) -> list[PlayerMove]:
        rows = self.conn.execute(
            "SELECT * FROM player_moves WHERE player_id = ?", (player_id,)
        ).fetchall()
        return [_row_to_move(r) for r in rows]

    def played_in_position(self, player_id: int, fen: str) -> list[tuple[str, int]]:
        """Every move the player actually made from a given position.

        `player_moves.fen` stores the position the move was made *in* (see the
        module/parsing notes on this deliberate choice), so a position recurring
        in a live game can be matched directly. Position identity ignores the
        move-clock fields (a position is the same regardless of the halfmove/
        fullmove counters), so we compare on a `position_key` — the first four
        FEN fields. Returns ``(san, times_played)`` pairs, most-played first.
        """
        from collections import Counter
        key = position_key(fen)
        played = [
            r["move_played"]
            for r in self.conn.execute(
                "SELECT move_played, fen FROM player_moves WHERE player_id = ?",
                (player_id,),
            )
            if position_key(r["fen"]) == key
        ]
        # Deterministic order: by count desc, then SAN — so a seeded weighted
        # pick is reproducible. Counter.most_common() breaks ties by insertion
        # order, which follows the unordered SQL scan and is non-deterministic.
        return sorted(Counter(played).items(), key=lambda kv: (-kv[1], kv[0]))

    def repertoire(self, player_id: int) -> dict[str, list[tuple[str, int]]]:
        """The player's entire repertoire as ``{position_key: [(san, count)]}``.

        Built in a single pass so the clone engine can load it once and look up
        moves in-memory at play time — no per-move SQL, and no cross-thread
        SQLite access from the AI worker thread.
        """
        from collections import Counter, defaultdict
        by_pos: dict[str, Counter] = defaultdict(Counter)
        for r in self.conn.execute(
            "SELECT move_played, fen FROM player_moves WHERE player_id = ?",
            (player_id,),
        ):
            by_pos[position_key(r["fen"])][r["move_played"]] += 1
        # Deterministic order (count desc, then SAN); see played_in_position.
        return {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
                for k, c in by_pos.items()}

    def count(self, player_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM player_moves WHERE player_id = ?",
            (player_id,),
        ).fetchone()["n"]


class StyleRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, profile: StyleProfile) -> StyleProfile:
        cur = self.conn.execute(
            """INSERT INTO player_styles
               (player_id, aggression, tactical, risk, king_safety, endgame,
                opening_preferences, style_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(player_id) DO UPDATE SET
                   aggression = excluded.aggression,
                   tactical = excluded.tactical,
                   risk = excluded.risk,
                   king_safety = excluded.king_safety,
                   endgame = excluded.endgame,
                   opening_preferences = excluded.opening_preferences,
                   style_json = excluded.style_json,
                   updated_at = datetime('now')
               RETURNING id, updated_at""",
            (profile.player_id, profile.aggression, profile.tactical,
             profile.risk, profile.king_safety, profile.endgame,
             json.dumps(profile.opening_preferences),
             json.dumps(profile.style_json)),
        )
        row = cur.fetchone()
        self.conn.commit()
        profile.id, profile.updated_at = row["id"], row["updated_at"]
        return profile

    def get(self, player_id: int) -> Optional[StyleProfile]:
        row = self.conn.execute(
            "SELECT * FROM player_styles WHERE player_id = ?", (player_id,)
        ).fetchone()
        return _row_to_style(row) if row else None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def position_key(fen: str) -> str:
    """Position identity for repertoire lookup: first four FEN fields."""
    return " ".join(fen.split()[:4])


def _row_to_player(r: sqlite3.Row) -> Player:
    return Player(id=r["id"], username=r["username"], display_name=r["display_name"],
                  source=r["source"], created_at=r["created_at"])


def _row_to_game(r: sqlite3.Row) -> Game:
    return Game(id=r["id"], player_id=r["player_id"], date=r["date"],
                color=r["color"], result=r["result"], opening=r["opening"],
                eco=r["eco"], time_control=r["time_control"],
                opponent_name=r["opponent_name"], opponent_rating=r["opponent_rating"],
                move_count=r["move_count"], pgn=r["pgn"], created_at=r["created_at"])


def _row_to_move(r: sqlite3.Row) -> PlayerMove:
    return PlayerMove(id=r["id"], player_id=r["player_id"], game_id=r["game_id"],
                      move_number=r["move_number"], fen=r["fen"],
                      move_played=r["move_played"], opening=r["opening"],
                      phase=r["phase"], evaluation=r["evaluation"],
                      mover=r["mover"], created_at=r["created_at"])


def _row_to_style(r: sqlite3.Row) -> StyleProfile:
    return StyleProfile(
        id=r["id"], player_id=r["player_id"], aggression=r["aggression"],
        tactical=r["tactical"], risk=r["risk"], king_safety=r["king_safety"],
        endgame=r["endgame"],
        opening_preferences=json.loads(r["opening_preferences"]),
        style_json=json.loads(r["style_json"]), updated_at=r["updated_at"])
