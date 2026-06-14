"""Flask REST API for the chess engine.

Endpoints
---------
POST /api/game/new          – start a fresh game
GET  /api/game/state        – current board + metadata
POST /api/game/move         – player makes a move (UCI: "e2e4")
GET  /api/game/legal?sq=e2  – legal destination squares for a piece
POST /api/game/ai           – ask the active opponent to play one move
POST /api/game/resign       – resign the current game
GET  /api/game/history      – full move list as SAN
GET  /api/samay/dna         – Samay Raina's style DNA profile
"""

from __future__ import annotations

import os
import threading
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import engine
from engine import (
    State, legal_moves, make_move, in_check,
    find_king, game_status, to_san, search_best_move, opp, sq_name, sq_index,
)
from player_clones.fen import state_to_fen
from player_clones.personality import SamayCommentator

# Resolve the frontend directory absolutely so it works no matter what working
# directory the server is launched from (gunicorn on Render, etc.).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)

SAMAY_USERNAME = "samayraina"

# Web UI sends difficulty as 1/2/3; the engine keys its search table by name.
_DIFFICULTY_LEVELS = {1: "easy", 2: "medium", 3: "hard"}

# The Samay clone is built once lazily in a background thread and reused.
# Two sources, in priority order:
#   1. The full local SQLite database, if a real import is present (best — the
#      complete 585k-position repertoire). Used in local development.
#   2. The committed, gzipped book artifact (player_clones/data/samay_book.json.gz)
#      — a few hundred KB, no games table, no network. Used on deploy where the
#      full DB is gitignored and absent.
# Both managers expose the same .get(mode_key, user_rating) interface.
_mode_manager = None
_manager_lock = threading.Lock()
_manager_ready = threading.Event()


def _build_manager():
    global _mode_manager
    try:
        mgr = _make_manager()
        with _manager_lock:
            _mode_manager = mgr
    except Exception as exc:
        print(f"[Samay] clone build failed: {exc}")
    finally:
        _manager_ready.set()   # unblock waiters even on failure


def _make_manager():
    """Pick the best available clone source: full DB, else book artifact."""
    from player_clones.db import Database, DEFAULT_DB_PATH

    # 1. Full local database with a real import (>100 games rules out the sample).
    if os.path.exists(DEFAULT_DB_PATH):
        try:
            db = Database()
            player = db.players.get_by_username(SAMAY_USERNAME)
            if player and db.games.count(player.id) >= 100:
                from player_clones.modes.samay_mode_manager import SamayModeManager
                print("[Samay] using full local database")
                return SamayModeManager()
        except Exception as exc:
            print(f"[Samay] full DB unavailable ({exc}); trying book artifact")

    # 2. Committed book artifact (the deploy path). Prefers the on-disk SQLite
    #    artifact, which holds all 585k positions at near-zero RAM — so the full
    #    clone fits on a 512 MB free instance.
    from player_clones.book import BookModeManager, book_artifact_exists
    if book_artifact_exists():
        print("[Samay] using committed book artifact")
        return BookModeManager.load()

    # 3. Last resort: let SamayModeManager bootstrap (bundled sample / live import).
    from player_clones.modes.samay_mode_manager import SamayModeManager
    print("[Samay] no DB or artifact found; bootstrapping clone")
    return SamayModeManager()


def _get_manager():
    """Return the shared clone manager, blocking briefly if it's still loading."""
    _manager_ready.wait(timeout=30)
    with _manager_lock:
        return _mode_manager


# Start building the manager in the background immediately so it's ready by
# the time the player hits "Start Game" with Samay selected.
threading.Thread(target=_build_manager, daemon=True).start()


# ---------------------------------------------------------------------------
# In-memory game store
# ---------------------------------------------------------------------------

class Game:
    def __init__(self):
        self.state = State()
        self.history: list[dict] = []
        self.over = False
        self.winner: str | None = None
        self.status_text = ""
        self.player_color = "w"
        self.difficulty = 2
        self.opponent = "engine"        # "engine" | "samay"
        self.clone_mode = "real"        # casual | real | peak
        self.fullmove = 1
        self._lock = threading.Lock()

        # Samay-specific (set when opponent=="samay")
        self._clone_provider = None     # ModedCloneProvider
        self._commentator: SamayCommentator | None = None
        self.last_banter: str = ""

    # ------------------------------------------------------------------
    def init_samay(self):
        """Build the moded clone provider and commentator for this game."""
        mgr = _get_manager()
        if mgr is None:
            return False
        try:
            self._clone_provider = mgr.get(self.clone_mode)
            self._commentator = SamayCommentator(mode_key=self.clone_mode)
            self.last_banter = self._commentator.game_start()
            return True
        except Exception as exc:
            print(f"[Samay] init failed: {exc}")
            return False

    def _copy_state(self) -> State:
        s = State()
        s.board = self.state.board[:]
        s.turn = self.state.turn
        s.castling = self.state.castling
        s.ep = self.state.ep
        s.halfmove = self.state.halfmove
        return s

    def serialize(self) -> dict:
        s = self.state
        lm = legal_moves(s)
        moves_by_sq: dict[str, list[str]] = {}
        for m in lm:
            frm = sq_name(m.frm)
            dst = sq_name(m.to) + (m.promo.lower() if m.promo else "")
            moves_by_sq.setdefault(frm, []).append(dst)

        in_chk = in_check(s, s.turn)
        king_sq = sq_name(find_king(s.board, s.turn)) if in_chk else None

        return {
            "board": s.board,
            "turn": s.turn,
            "over": self.over,
            "winner": self.winner,
            "statusText": self.status_text,
            "playerColor": self.player_color,
            "difficulty": self.difficulty,
            "opponent": self.opponent,
            "cloneMode": self.clone_mode,
            "legalMoves": moves_by_sq,
            "inCheck": in_chk,
            "kingSquare": king_sq,
            "history": self.history,
            "lastMove": (
                {"from": self.history[-1]["from"], "to": self.history[-1]["to"]}
                if self.history else None
            ),
            "banter": self.last_banter,
        }

    def apply_uci(self, uci: str, meta: dict | None = None) -> dict[str, Any]:
        with self._lock:
            if self.over:
                return {"error": "Game is already over"}

            frm = sq_index(uci[:2])
            to  = sq_index(uci[2:4])
            promo = uci[4].upper() if len(uci) == 5 else None

            lm = legal_moves(self.state)
            move = next(
                (m for m in lm if m.frm == frm and m.to == to
                 and (m.promo or "").upper() == (promo or "")),
                None,
            )
            if move is None:
                return {"error": f"Illegal move: {uci}"}

            san = to_san(self.state, move)
            captured = self.state.board[move.to]
            make_move(self.state, move)

            if self.state.turn == "w":
                self.fullmove += 1

            entry = {
                "uci": uci,
                "san": san,
                "captured": captured,
                "from": sq_name(frm),
                "to": sq_name(to),
            }
            if meta:
                entry.update(meta)
            self.history.append(entry)

            over, winner, text = game_status(self.state)
            self.over, self.winner, self.status_text = over, winner, text

            # game-over banter
            if self.over and self._commentator:
                clone_color = opp(self.player_color)
                clone_won = (self.winner == clone_color) if self.winner else None
                self.last_banter = self._commentator.on_game_over(clone_won)

            return self.serialize()

    # ------------------------------------------------------------------
    def ai_move(self) -> dict[str, Any]:
        with self._lock:
            if self.over:
                return {"error": "Game is already over"}
            if self.state.turn == self.player_color:
                return {"error": "It is the player's turn"}
            state_copy = self._copy_state()
            opponent = self.opponent
            provider = self._clone_provider

        if opponent == "samay":
            if provider is None:
                return {"error": "Samay clone is still loading — try again in a moment"}
            try:
                decision = provider.decide(state_copy)
                if decision.move is None:
                    return {"error": "Samay clone returned no move"}
                uci = decision.move.uci()

                # generate banter from this move's metadata
                banter = ""
                if self._commentator:
                    banter = self._commentator.on_clone_move(
                        san=decision.san,
                        source=decision.source,
                        contributions=decision.contributions,
                        eval_cp=decision.eval_cp,
                    )

                meta = {
                    "source": decision.source,
                    "styleScore": decision.style_score,
                    "banter": banter,
                }
                result = self.apply_uci(uci, meta)
                if "error" not in result:
                    self.last_banter = banter
                    result["banter"] = banter
                return result
            except Exception as exc:
                return {"error": f"Samay clone error: {exc}"}
        else:
            level = _DIFFICULTY_LEVELS.get(self.difficulty, "medium")
            best, _score, _nodes = search_best_move(state_copy, level)
            if best is None:
                return {"error": "No moves available"}
            return self.apply_uci(best.uci())


_game = Game()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path):
    # Serve any real asset under frontend/; otherwise fall back to index.html.
    if path and os.path.isfile(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/game/new", methods=["POST"])
def new_game():
    global _game
    data = request.get_json(silent=True) or {}
    g = Game()
    g.player_color = data.get("playerColor", "w")
    g.difficulty   = int(data.get("difficulty", 2))
    g.opponent     = data.get("opponent", "engine")
    g.clone_mode   = data.get("cloneMode", "real")

    if g.opponent == "samay":
        ok = g.init_samay()
        if not ok:
            g.last_banter = "Clone loading, give it a second..."

    _game = g
    return jsonify(_game.serialize())


@app.route("/api/game/state")
def get_state():
    return jsonify(_game.serialize())


@app.route("/api/game/move", methods=["POST"])
def make_player_move():
    data = request.get_json(silent=True) or {}
    uci = data.get("uci", "")
    if not uci:
        return jsonify({"error": "Missing 'uci' field"}), 400
    result = _game.apply_uci(uci)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/game/ai", methods=["POST"])
def ai_move():
    result = _game.ai_move()
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/game/legal")
def legal():
    sq = request.args.get("sq", "")
    if len(sq) != 2:
        return jsonify({"error": "Pass ?sq=e2"}), 400
    idx = sq_index(sq)
    lm = legal_moves(_game.state)
    dsts = [sq_name(m.to) + (m.promo.lower() if m.promo else "")
            for m in lm if m.frm == idx]
    return jsonify({"from": sq, "targets": dsts})


@app.route("/api/game/resign", methods=["POST"])
def resign():
    _game.over = True
    _game.winner = opp(_game.player_color)
    _game.status_text = "You resigned"
    if _game._commentator:
        _game.last_banter = _game._commentator.on_game_over(clone_won=True)
    return jsonify(_game.serialize())


@app.route("/api/game/history")
def history():
    return jsonify({"history": _game.history})


@app.route("/api/samay/dna")
def samay_dna():
    mgr = _get_manager()
    if mgr is None:
        return jsonify({"error": "Clone not ready yet"}), 503
    try:
        provider = mgr.get("real")
        return jsonify(provider.dna())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/samay/ready")
def samay_ready():
    return jsonify({"ready": _mode_manager is not None})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Chess API running at http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
