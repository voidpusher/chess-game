"""Command-line entry point for the Player Clone system.

    python -m player_clones.cli import samayraina           # bounded live import
    python -m player_clones.cli import samayraina --full     # unlimited backfill
    python -m player_clones.cli import samayraina --all      # alias for --full
    python -m player_clones.cli import samayraina --sample   # offline sample
    python -m player_clones.cli sync  samayraina            # incremental refresh
    python -m player_clones.cli analyze samayraina          # (re)build fingerprint
    python -m player_clones.cli dna   samayraina            # print DNA as JSON
    python -m player_clones.cli serve                       # run the HTTP API
"""

from __future__ import annotations

import argparse
import json
import sys

from player_clones.db import Database
from player_clones.importer.player_importer import PlayerImporterService
from player_clones.importer.chesscom_client import ChessComClient, ChessComError
from player_clones.importer.sample_data import SampleChessComClient
from player_clones.style_analysis.style_analyzer import PlayerStyleAnalyzer
from player_clones.providers.factory import create_player_clone


def _importer(db, sample):
    client = SampleChessComClient() if sample else ChessComClient()
    return PlayerImporterService(db, client=client)


def cmd_import(args):
    db = Database(args.db)
    full = getattr(args, "full", False) or getattr(args, "all", False)
    if full and not args.sample:
        print(f"Importing FULL history for '{args.username}' "
              f"(all archives, no game cap) — this may take a while...")
        # Unlimited backfill: no archive/game limits at all.
        summary = _importer(db, args.sample).import_player(
            args.username, max_archives=None, max_games=None)
    else:
        if not args.sample:
            print(f"Importing recent games for '{args.username}' "
                  f"(bounded bootstrap; use --full for everything)...")
        summary = _importer(db, args.sample).import_player(args.username)
    print(summary)
    print(f"  -> {summary.games_new} new game(s), {summary.games_total} total, "
          f"{summary.moves_added} move(s) added from "
          f"{summary.archives_scanned} archive(s).")
    profile = PlayerStyleAnalyzer(db).analyze(summary.player_id)
    print("fingerprint:", json.dumps(profile.headline()))


def cmd_sync(args):
    db = Database(args.db)
    summary = _importer(db, args.sample).sync_player(args.username)
    print(summary)
    player = db.players.get_by_username(args.username)
    if player:
        PlayerStyleAnalyzer(db).analyze(player.id)
        print("fingerprint refreshed")


def cmd_analyze(args):
    db = Database(args.db)
    player = db.players.get_by_username(args.username)
    if not player:
        sys.exit(f"unknown player '{args.username}' — import first")
    profile = PlayerStyleAnalyzer(db).analyze(player.id)
    print(json.dumps(profile.style_json, indent=2))


def cmd_dna(args):
    db = Database(args.db)
    source = "sample" if args.sample else "auto"
    provider = create_player_clone(args.username, db=db, source=source)
    print(json.dumps(provider.dna(), indent=2))


def cmd_serve(args):
    from player_clones.api import serve
    serve(host=args.host, port=args.port, db=Database(args.db))


def build_parser():
    p = argparse.ArgumentParser(prog="player_clones",
                                description="Player Clone Engine CLI")
    p.add_argument("--db", default=None, help="SQLite path (default: package data dir)")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn, needs_user in (("import", cmd_import, True),
                                 ("sync", cmd_sync, True),
                                 ("analyze", cmd_analyze, True),
                                 ("dna", cmd_dna, True)):
        sp = sub.add_parser(name)
        if needs_user:
            sp.add_argument("username")
        sp.add_argument("--sample", action="store_true",
                        help="use the bundled offline sample instead of the network")
        if name == "import":
            sp.add_argument("--full", action="store_true",
                            help="remove archive/game limits — import the player's "
                                 "entire public history")
            sp.add_argument("--all", action="store_true",
                            help="alias for --full")
        sp.set_defaults(func=fn)

    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(func=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    # default db path handled by Database() when None
    if args.db is None:
        from player_clones.db import DEFAULT_DB_PATH
        args.db = DEFAULT_DB_PATH
    try:
        args.func(args)
    except ChessComError as e:
        sys.exit(f"Chess.com error: {e}")


if __name__ == "__main__":
    main()
