"""PGN text utilities + game replay (PHASE 2).

Two layers:

* **Text layer** (`split_pgn`, `tokenize_movetext`, `game_metadata`) — pure
  string handling, no chess knowledge. The importer uses these to turn a
  Chess.com PGN into a `Game` row.
* **Replay layer** (`PgnParser`) — replays the SAN movetext through the existing
  `engine` to produce one `PlayerMove` per move the *cloned player* made,
  capturing the pre-move FEN, opening, phase, and post-move evaluation.

Nothing here generates moves or validates legality independently — it leans
entirely on `engine.parse_san` / `engine.make_move`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import engine
from engine import State, make_move
from player_clones import fen as fenutil
from player_clones.models import Game, PlayerMove

_HEADER_RE = re.compile(r'\[(\w+)\s+"(.*?)"\]')
_COMMENT_RE = re.compile(r"\{[^}]*\}")
_NAG_RE = re.compile(r"\$\d+")
_MOVENUM_RE = re.compile(r"\d+\.(\.\.)?")
_RESULTS = {"1-0", "0-1", "1/2-1/2", "*"}

# Chess.com / PGN per-side result codes that are not wins, split into draw vs loss.
_DRAW_CODES = {
    "agreed", "repetition", "stalemate", "insufficient",
    "50move", "timevsinsufficient", "draw",
}


# --------------------------------------------------------------------------- #
# Text layer
# --------------------------------------------------------------------------- #

@dataclass
class ParsedGame:
    headers: dict
    san_moves: list[str]
    raw_pgn: str = ""


def split_pgn(pgn: str) -> tuple[dict, str]:
    """Return ``(headers, movetext)`` for a single PGN string."""
    headers = {k: v for k, v in _HEADER_RE.findall(pgn)}
    # Movetext is everything after the last header line (the blank-line split is
    # unreliable across exporters, so we strip recognised header lines instead).
    lines = [ln for ln in pgn.splitlines() if not ln.strip().startswith("[")]
    movetext = " ".join(lines).strip()
    return headers, movetext


def _strip_variations(text: str) -> str:
    """Remove (possibly nested) parenthesised variations."""
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def tokenize_movetext(movetext: str) -> list[str]:
    """Extract the ordered list of SAN tokens from PGN movetext.

    Strips comments, NAGs, variations, move numbers and the result token.
    """
    text = _COMMENT_RE.sub(" ", movetext)
    text = _strip_variations(text)
    text = _NAG_RE.sub(" ", text)
    tokens = []
    for tok in text.split():
        if tok in _RESULTS:
            continue
        tok = _MOVENUM_RE.sub("", tok)      # "12.Nf3" -> "Nf3", "12." -> ""
        tok = tok.strip(".")
        if tok:
            tokens.append(tok)
    return tokens


def parse_pgn(pgn: str) -> ParsedGame:
    headers, movetext = split_pgn(pgn)
    return ParsedGame(headers=headers, san_moves=tokenize_movetext(movetext),
                      raw_pgn=pgn)


def _result_for(side_result: str) -> str:
    if side_result == "win":
        return "win"
    if side_result in _DRAW_CODES:
        return "draw"
    return "loss"


def game_metadata(pgn: str, username: str,
                  game_json: Optional[dict] = None) -> Game:
    """Build a `Game` row (minus player_id) from a PGN and optional API json.

    Structured fields come from the Chess.com game json when available (it is
    authoritative for ratings/results); opening name and dates fall back to PGN
    headers. `player_id` is filled in by the importer.
    """
    parsed = parse_pgn(pgn)
    h = parsed.headers
    uname = username.lower()

    # Determine the cloned player's colour.
    white = (h.get("White") or "").lower()
    color = "white" if white == uname else "black"

    # Result + opponent + ratings: prefer the API json, fall back to headers.
    if game_json:
        side = game_json.get(color, {})
        opp_side = game_json.get("black" if color == "white" else "white", {})
        result = _result_for(side.get("result", ""))
        opponent_name = opp_side.get("username", "")
        opponent_rating = opp_side.get("rating")
        time_control = game_json.get("time_control", h.get("TimeControl", ""))
    else:
        # Derive from the PGN result tag relative to colour.
        tag = h.get("Result", "*")
        if tag == "1/2-1/2":
            result = "draw"
        elif tag == "1-0":
            result = "win" if color == "white" else "loss"
        elif tag == "0-1":
            result = "win" if color == "black" else "loss"
        else:
            result = "unknown"
        opponent_name = (h.get("Black") if color == "white" else h.get("White")) or ""
        rating_tag = "BlackElo" if color == "white" else "WhiteElo"
        opponent_rating = _to_int(h.get(rating_tag))
        time_control = h.get("TimeControl", "")

    opening = _opening_name(h)
    eco = h.get("ECO", "")
    date = h.get("UTCDate") or h.get("Date") or ""

    return Game(
        player_id=0, date=date, color=color, result=result,
        opening=opening, eco=eco, time_control=time_control,
        opponent_name=opponent_name, opponent_rating=opponent_rating,
        move_count=(len(parsed.san_moves) + 1) // 2, pgn=pgn,
    )


def _opening_name(headers: dict) -> str:
    """Human-readable opening name from headers (ECOUrl slug or Opening tag).

    Chess.com ECOUrl slugs embed the whole variation, e.g.
    ``Ruy-Lopez-Old-Steinitz-Defense-5.Qxd4-Bd7-6.Bxc6`` — we keep only the
    named part by cutting at the first move-number token (``5.Qxd4``).
    """
    if headers.get("Opening"):
        return headers["Opening"]
    url = headers.get("ECOUrl") or headers.get("ECOurl") or ""
    if url:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        parts = []
        for token in slug.split("-"):
            if re.match(r"^\d+\.?", token):          # first move number -> stop
                break
            parts.append(token)
        while parts and parts[-1].lower() in {"with", "and", "the", "of", "a", "in"}:
            parts.pop()
        name = " ".join(parts).strip()
        if name:
            return name
    return headers.get("ECO", "") or "Unknown"


def _to_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Replay layer
# --------------------------------------------------------------------------- #

class PgnParser:
    """Replays a stored `Game` and emits the cloned player's `PlayerMove` rows.

    Only the moves the *cloned player* made are emitted — those are the moves
    that define the player's style and repertoire. For each such move we record
    the position it was made in (pre-move FEN), the SAN, the phase, the opening,
    and the static evaluation of the resulting position.
    """

    def parse_moves(self, game: Game) -> list[PlayerMove]:
        parsed = parse_pgn(game.pgn)
        player_color = "w" if game.color == "white" else "b"
        state = State()
        out: list[PlayerMove] = []

        from player_clones.pgn_parser.fast_san import match_san
        for ply, san in enumerate(parsed.san_moves):
            move = match_san(state, san)
            if move is None:
                # Illegal/unparseable token: stop replaying this game rather than
                # corrupting the dataset. Partial games still contribute.
                break

            move_number = ply // 2 + 1
            if state.turn == player_color:
                pre_fen = fenutil.state_to_fen(state, move_number)
                phase = fenutil.classify_phase(state, move_number)
                make_move(state, move)
                # eval AFTER the move, normalised to White's perspective (cp)
                ev = engine.evaluate(state)
                ev_white = ev if state.turn == "b" else -ev
                out.append(PlayerMove(
                    player_id=game.player_id, game_id=game.id or 0,
                    move_number=move_number, fen=pre_fen, move_played=san,
                    opening=game.opening, phase=phase, evaluation=int(ev_white),
                    mover=player_color,
                ))
            else:
                make_move(state, move)
        return out
