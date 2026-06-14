"""API layer (FINAL DELIVERABLE: "API routes").

The host app is a desktop GUI, not a web server, so the public surface is a
clean service **facade** whose methods map one-to-one to the REST routes a web
front-end would expose. The mapping is documented in `ROUTES`, and `serve()`
spins up a real stdlib HTTP server over the same facade when you do want HTTP —
no framework, no new dependencies.

    api = PlayerCloneAPI()
    api.import_player("samayraina")          # POST /players/import
    api.get_dna("samayraina")                # GET  /players/{u}/dna
    api.choose_move("samayraina", fen)       # POST /clone/{u}/move

REST mapping (method, path -> facade call):

    POST /players/import          {username}        -> import_player
    POST /players/{u}/sync                          -> sync_player
    GET  /players/{u}/style                         -> get_style
    GET  /players/{u}/dna                            -> get_dna
    POST /clone/{u}/move          {fen}             -> choose_move
"""

from __future__ import annotations

from typing import Optional

import engine
from player_clones.db import Database
from player_clones.models import StyleProfile
from player_clones.importer.player_importer import PlayerImporterService
from player_clones.importer.chesscom_client import ChessComClient
from player_clones.style_analysis.style_analyzer import PlayerStyleAnalyzer
from player_clones.providers.factory import create_player_clone
from player_clones import fen as fenutil

ROUTES = {
    ("POST", "/players/import"): "import_player",
    ("POST", "/players/{username}/sync"): "sync_player",
    ("GET", "/players/{username}/style"): "get_style",
    ("GET", "/players/{username}/dna"): "get_dna",
    ("POST", "/clone/{username}/move"): "choose_move",
}


class PlayerCloneAPI:
    """Stateless-ish facade over the clone services (one shared DB)."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self._providers: dict = {}

    # ---- ingestion ----------------------------------------------------- #
    def import_player(self, username: str, full: bool = True) -> dict:
        importer = PlayerImporterService(self.db, client=ChessComClient())
        summary = (importer.import_player(username) if full
                   else importer.sync_player(username))
        self._invalidate(username)
        return summary.__dict__

    def sync_player(self, username: str) -> dict:
        importer = PlayerImporterService(self.db, client=ChessComClient())
        summary = importer.sync_player(username)
        self._invalidate(username)
        return summary.__dict__

    def analyze_player(self, username: str) -> dict:
        player = self.db.players.get_by_username(username)
        if not player:
            raise KeyError(f"unknown player: {username}")
        profile = PlayerStyleAnalyzer(self.db).analyze(player.id)
        return profile.headline()

    # ---- reads --------------------------------------------------------- #
    def get_style(self, username: str) -> dict:
        player = self.db.players.get_by_username(username)
        prof = self.db.styles.get(player.id) if player else None
        if not prof:
            raise KeyError(f"no style profile for {username}; import + analyze first")
        return {"headline": prof.headline(), "style": prof.style_json}

    def get_dna(self, username: str) -> dict:
        return self._provider(username).dna()

    # ---- gameplay ------------------------------------------------------ #
    def choose_move(self, username: str, fen: str) -> dict:
        state = engine.from_fen(fen)
        decision = self._provider(username).decide(state)
        return {
            "move": decision.move.uci() if decision.move else None,
            "san": decision.san,
            "source": decision.source,
            "eval_cp": decision.eval_cp,
            "style_score": decision.style_score,
            "contributions": decision.contributions,
        }

    # ---- internals ----------------------------------------------------- #
    def _provider(self, username: str):
        if username not in self._providers:
            self._providers[username] = create_player_clone(username, db=self.db)
        return self._providers[username]

    def _invalidate(self, username: str) -> None:
        self._providers.pop(username.lower(), None)


def serve(host: str = "127.0.0.1", port: int = 8765,
          db: Optional[Database] = None):
    """Expose the facade over HTTP using only the standard library."""
    import json
    import re
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    api = PlayerCloneAPI(db)
    compiled = [(m, re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", p) + "$"),
                 fn) for (m, p), fn in ROUTES.items()]

    class Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method):
            body = {}
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except ValueError:
                    body = {}
            for m, rx, fn in compiled:
                if m != method:
                    continue
                match = rx.match(self.path.split("?")[0])
                if not match:
                    continue
                kwargs = {**match.groupdict(), **body}
                try:
                    result = getattr(api, fn)(**kwargs)
                    self._send(200, result)
                except Exception as e:  # noqa: BLE001 - surface as JSON error
                    self._send(400, {"error": str(e)})
                return
            self._send(404, {"error": "no route"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def _send(self, code, payload):
            data = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):  # quiet
            pass

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Player Clone API on http://{host}:{port}")
    httpd.serve_forever()
