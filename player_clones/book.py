"""Deployment artifact: a compact, self-contained Samay clone.

The full clone normally reads a ~330 MB SQLite database (21k games, 697k move
rows). That database is gitignored and far too large to ship. But at *play time*
the clone only needs three things:

    * the **repertoire** ({position_key: [(san, count), ...]}),
    * the **style profile** (the 0-100 fingerprint + breakdown), and
    * a **total game count** (for the DNA page).

This module exports exactly those into a tiny artifact and loads a fully
mode-aware provider back from it — no games table, no network. The artifact is
committed to the repo so the web app deploys anywhere (Render, Railway, Fly, …)
without an import step.

Two artifact formats:

    * **SQLite** (`samay_book.sqlite.gz`, preferred) — the repertoire lives on
      disk and each position is fetched with one indexed query. The full 585k
      positions cost almost no RAM, so it runs on a 512 MB free instance. This
      is what the deployed server uses.
    * **JSON** (`samay_book.json.gz`, legacy) — loads the whole repertoire into a
      dict (~200 MB RAM for the full set). Fine locally, too heavy for free tiers.

    # build (run once, locally, after a full import):
    python -m player_clones.book export samayraina          # SQLite (default)
    python -m player_clones.book export samayraina --json   # legacy JSON

    # load (used by the web server when the full DB isn't present):
    mgr = BookModeManager.load()        # auto-detects the artifact
    provider = mgr.get("real")          # ModedCloneProvider, ready to play
"""

from __future__ import annotations

import gzip
import json
import os
import random
import shutil
import sqlite3
import tempfile
from typing import Optional

from player_clones.models import Player, StyleProfile
from player_clones.providers.player_clone_provider import PlayerCloneProvider
from player_clones.providers.base_provider import CloneProvider
from player_clones.modes.mode_config import MODE_PRESETS, adaptive_config
from player_clones.modes.moded_provider import ModedCloneProvider

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SQLITE_BOOK_PATH = os.path.join(_DATA_DIR, "samay_book.sqlite.gz")
JSON_BOOK_PATH = os.path.join(_DATA_DIR, "samay_book.json.gz")
DEFAULT_BOOK_PATH = JSON_BOOK_PATH   # back-compat alias

# Keep every position by default so the deployed bot is identical to the local
# full-database version. With the SQLite artifact this is free (positions live
# on disk); pass a higher min_count only if you want a smaller file.
DEFAULT_MIN_COUNT = 1


# --------------------------------------------------------------------------- #
# Shared: build the repertoire dict from the database
# --------------------------------------------------------------------------- #

def _build_repertoire(db, player_id: int, min_count: int) -> dict:
    from collections import Counter, defaultdict
    from player_clones.db import position_key

    by_pos: dict[str, Counter] = defaultdict(Counter)
    for r in db.conn.execute(
            "SELECT move_played, fen FROM player_moves WHERE player_id = ?",
            (player_id,)):
        by_pos[position_key(r["fen"])][r["move_played"]] += 1

    repertoire = {}
    for key, counter in by_pos.items():
        if sum(counter.values()) < min_count:
            continue
        repertoire[key] = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return repertoire


def _player_meta(db, username: str):
    player = db.players.get_by_username(username)
    if not player:
        raise KeyError(f"unknown player '{username}' — import first")
    profile = db.styles.get(player.id)
    if not profile:
        raise KeyError(f"no style profile for '{username}' — analyze first")
    return player, profile


def _profile_dict(profile) -> dict:
    return {
        "aggression": profile.aggression, "tactical": profile.tactical,
        "risk": profile.risk, "king_safety": profile.king_safety,
        "endgame": profile.endgame,
        "opening_preferences": profile.opening_preferences,
        "style_json": profile.style_json,
    }


def _make_profile(player_id: int, pf: dict) -> StyleProfile:
    return StyleProfile(
        player_id=player_id,
        aggression=pf["aggression"], tactical=pf["tactical"], risk=pf["risk"],
        king_safety=pf["king_safety"], endgame=pf["endgame"],
        opening_preferences=pf.get("opening_preferences", {}),
        style_json=pf.get("style_json", {}))


# --------------------------------------------------------------------------- #
# SQLite artifact (preferred)
# --------------------------------------------------------------------------- #

def export_book_sqlite(db, username: str, out_path: str = SQLITE_BOOK_PATH,
                       min_count: int = DEFAULT_MIN_COUNT) -> dict:
    """Export the clone essentials to a gzipped SQLite artifact."""
    player, profile = _player_meta(db, username)
    repertoire = _build_repertoire(db, player.id, min_count)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path[:-3] if out_path.endswith(".gz") else out_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)

    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE repertoire (pos TEXT PRIMARY KEY, moves TEXT)")
    con.executemany(
        "INSERT INTO repertoire (pos, moves) VALUES (?, ?)",
        ((k, json.dumps(v, separators=(",", ":"))) for k, v in repertoire.items()))
    con.executemany(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        [
            ("player", json.dumps({"username": player.username,
                                   "display_name": player.display_name,
                                   "source": player.source})),
            ("profile", json.dumps(_profile_dict(profile))),
            ("total_games", str(db.games.count(player.id))),
            ("min_count", str(min_count)),
        ])
    con.commit()
    con.execute("VACUUM")
    con.close()

    with open(tmp, "rb") as f_in, gzip.open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(tmp)

    return {"path": out_path, "positions": len(repertoire),
            "total_games": db.games.count(player.id),
            "bytes": os.path.getsize(out_path)}


class SqliteRepertoire:
    """Dict-like repertoire backed by an on-disk SQLite file (near-zero RAM).

    Exposes the only method the clone engine and ModedCloneProvider use —
    ``.get(key, default)`` — as a single indexed query, so it is a drop-in for
    the in-memory dict the providers normally hold.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, key: str, default=None):
        row = self._conn.execute(
            "SELECT moves FROM repertoire WHERE pos = ?", (key,)).fetchone()
        if row is None:
            return default
        return [(san, int(n)) for san, n in json.loads(row[0])]

    def __len__(self):
        return self._conn.execute(
            "SELECT COUNT(*) FROM repertoire").fetchone()[0]


def load_book_provider_sqlite(path: str = SQLITE_BOOK_PATH,
                              rng: Optional[random.Random] = None
                              ) -> PlayerCloneProvider:
    # Decompress to a temp file once; SQLite then reads pages from disk on demand.
    fd, tmp = tempfile.mkstemp(prefix="samay_book_", suffix=".sqlite")
    os.close(fd)
    with gzip.open(path, "rb") as f_in, open(tmp, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    conn = sqlite3.connect(tmp, check_same_thread=False)
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM meta")}

    pinfo = json.loads(meta["player"])
    player = Player(username=pinfo["username"],
                    display_name=pinfo["display_name"],
                    source=pinfo.get("source", "chess.com"), id=1)
    profile = _make_profile(1, json.loads(meta["profile"]))

    return PlayerCloneProvider(
        db=None, player=player, profile=profile,
        repertoire=SqliteRepertoire(conn),
        total_games=int(meta.get("total_games", 0)), rng=rng)


# --------------------------------------------------------------------------- #
# JSON artifact (legacy / local)
# --------------------------------------------------------------------------- #

def export_book(db, username: str, out_path: str = JSON_BOOK_PATH,
                min_count: int = DEFAULT_MIN_COUNT) -> dict:
    """Export the clone essentials to a gzipped JSON artifact (loads into RAM)."""
    player, profile = _player_meta(db, username)
    repertoire = _build_repertoire(db, player.id, min_count)

    artifact = {
        "version": 1,
        "player": {"username": player.username,
                   "display_name": player.display_name, "source": player.source},
        "profile": _profile_dict(profile),
        "total_games": db.games.count(player.id),
        "min_count": min_count,
        "repertoire": repertoire,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    raw = json.dumps(artifact, separators=(",", ":")).encode("utf-8")
    with gzip.open(out_path, "wb") as fh:
        fh.write(raw)
    return {"path": out_path, "positions": len(repertoire),
            "total_games": artifact["total_games"],
            "bytes": os.path.getsize(out_path)}


def _load_json_artifact(path: str) -> dict:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def load_book_provider_json(path: str = JSON_BOOK_PATH,
                            rng: Optional[random.Random] = None
                            ) -> PlayerCloneProvider:
    art = _load_json_artifact(path)
    pinfo = art["player"]
    player = Player(username=pinfo["username"], display_name=pinfo["display_name"],
                    source=pinfo.get("source", "chess.com"), id=1)
    profile = _make_profile(1, art["profile"])
    # Hand the parsed lists straight through (the engine iterates `for san, n`),
    # so no second dict is built.
    return PlayerCloneProvider(
        db=None, player=player, profile=profile,
        repertoire=art["repertoire"], total_games=art.get("total_games", 0),
        rng=rng)


# --------------------------------------------------------------------------- #
# Auto-detecting loader + mode manager
# --------------------------------------------------------------------------- #

def load_book_provider(path: Optional[str] = None,
                       rng: Optional[random.Random] = None) -> PlayerCloneProvider:
    """Load from whichever artifact exists, preferring the low-RAM SQLite one."""
    if path:
        if path.endswith(".sqlite.gz"):
            return load_book_provider_sqlite(path, rng=rng)
        return load_book_provider_json(path, rng=rng)
    if os.path.exists(SQLITE_BOOK_PATH):
        return load_book_provider_sqlite(SQLITE_BOOK_PATH, rng=rng)
    if os.path.exists(JSON_BOOK_PATH):
        return load_book_provider_json(JSON_BOOK_PATH, rng=rng)
    raise FileNotFoundError("no Samay book artifact found in player_clones/data/")


def book_artifact_exists() -> bool:
    return os.path.exists(SQLITE_BOOK_PATH) or os.path.exists(JSON_BOOK_PATH)


class BookModeManager:
    """Mode views over an artifact-loaded clone — mirrors SamayModeManager.get."""

    def __init__(self, base: PlayerCloneProvider,
                 rng: Optional[random.Random] = None):
        self._base = base
        self._rng = rng

    @classmethod
    def load(cls, path: Optional[str] = None,
             rng: Optional[random.Random] = None) -> "BookModeManager":
        return cls(load_book_provider(path, rng=rng), rng=rng)

    def get(self, mode_key: str, user_rating: int = 1200) -> CloneProvider:
        if mode_key == "adaptive":
            config = adaptive_config(user_rating)
        else:
            config = MODE_PRESETS.get(mode_key)
            if config is None:
                raise KeyError(f"unknown mode: {mode_key!r}")
        return ModedCloneProvider(self._base, config, rng=self._rng)


# --------------------------------------------------------------------------- #
# CLI: python -m player_clones.book export samayraina
# --------------------------------------------------------------------------- #

def _main(argv=None):
    import argparse
    from player_clones.db import Database

    ap = argparse.ArgumentParser(prog="player_clones.book")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="export a clone artifact from the DB")
    ex.add_argument("username")
    ex.add_argument("--json", action="store_true",
                    help="export the legacy JSON artifact instead of SQLite")
    ex.add_argument("--out", default=None)
    ex.add_argument("--min-count", type=int, default=DEFAULT_MIN_COUNT)
    args = ap.parse_args(argv)

    if args.cmd == "export":
        db = Database()
        if args.json:
            out = args.out or JSON_BOOK_PATH
            info = export_book(db, args.username, out, args.min_count)
            kind = "JSON"
        else:
            out = args.out or SQLITE_BOOK_PATH
            info = export_book_sqlite(db, args.username, out, args.min_count)
            kind = "SQLite"
        print("Wrote {kind} artifact: {path}\n  {positions:,} positions, "
              "{total_games:,} games, {kb:.1f} KB".format(
                  kind=kind, kb=info["bytes"] / 1024, **info))


if __name__ == "__main__":
    _main()
