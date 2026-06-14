"""FEN serialisation, game-phase classification, and per-move feature extraction.

The existing `engine` module ships `from_fen` but no `to_fen`, and the Player
Clone system needs to persist a FEN after every move (PHASE 2) and to reason
about *features* of a move (check, capture, sacrifice, castling, ...) for the
style engine (PHASE 3) and the move scorer (PHASE 4).

All of that lives here so `engine.py` (existing gameplay) stays untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import engine
from engine import (
    CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ,
    VAL, State, Move, make_move, unmake_move, legal_moves, pseudo_moves,
    is_attacked, in_check, find_king, opp, sq_name,
)

# --------------------------------------------------------------------------- #
# Phase classification
# --------------------------------------------------------------------------- #

OPENING = "OPENING"
MIDDLEGAME = "MIDDLEGAME"
ENDGAME = "ENDGAME"

# Non-pawn, non-king material at the start of the game, summed over both sides.
_START_NPM = 2 * (2 * VAL["N"] + 2 * VAL["B"] + 2 * VAL["R"] + VAL["Q"])  # 6400


def non_pawn_material(board) -> int:
    """Combined value of every non-pawn, non-king piece on the board."""
    total = 0
    for p in board:
        if p and p[1] not in ("P", "K"):
            total += VAL[p[1]]
    return total


def classify_phase(state: State, move_number: int) -> str:
    """Bucket a position into OPENING / MIDDLEGAME / ENDGAME.

    Heuristic, but matches how players talk about phases:
      * ENDGAME once heavy material has been traded off, or queens are gone and
        only light material remains;
      * OPENING for the first ~10 full moves while the board is still full;
      * MIDDLEGAME otherwise.
    """
    npm = non_pawn_material(state.board)
    queens = sum(1 for p in state.board if p and p[1] == "Q")
    if npm <= 2000 or (queens == 0 and npm <= 3200):
        return ENDGAME
    if move_number <= 10 and npm >= _START_NPM - 1300:
        return OPENING
    return MIDDLEGAME


# --------------------------------------------------------------------------- #
# FEN serialisation
# --------------------------------------------------------------------------- #

def state_to_fen(state: State, fullmove: int = 1) -> str:
    """Serialise a `State` to a full six-field FEN string.

    The board layout is the engine's: index 0 = a8 ... 63 = h1, which is exactly
    FEN rank order (rank 8 first), so we can walk it straight through.
    """
    rows = []
    for r in range(8):
        row, empty = [], 0
        for c in range(8):
            p = state.board[r * 8 + c]
            if p is None:
                empty += 1
                continue
            if empty:
                row.append(str(empty))
                empty = 0
            row.append(p[1] if p[0] == "w" else p[1].lower())
        if empty:
            row.append(str(empty))
        rows.append("".join(row))
    placement = "/".join(rows)

    castle = "".join([
        "K" if state.castling & CASTLE_WK else "",
        "Q" if state.castling & CASTLE_WQ else "",
        "k" if state.castling & CASTLE_BK else "",
        "q" if state.castling & CASTLE_BQ else "",
    ]) or "-"

    ep = sq_name(state.ep) if state.ep >= 0 else "-"
    return f"{placement} {state.turn} {castle} {ep} {state.halfmove} {fullmove}"


# --------------------------------------------------------------------------- #
# Per-move feature extraction
# --------------------------------------------------------------------------- #

@dataclass
class MoveFeatures:
    """Style-relevant facts about a single move, computed by replaying it.

    Every flag is cheap to derive and provider-agnostic; the style analyzer
    aggregates them into a fingerprint and the scorer matches candidate moves
    against that fingerprint.
    """
    san: str = ""
    mover: str = "w"                 # 'w' / 'b' — side that made the move
    is_capture: bool = False
    captured_value: int = 0          # centipawns of the captured piece (0 if none)
    is_check: bool = False
    is_castle: bool = False
    is_promotion: bool = False
    gives_mate: bool = False
    develops_piece: bool = False     # minor piece leaving its back rank
    is_pawn_push: bool = False
    advances_into_enemy: bool = False  # piece moves into opponent's half
    central: bool = False            # lands on an extended-centre square
    is_sacrifice: bool = False       # gives up material not immediately regained
    creates_fork: bool = False       # lands a piece attacking >=2 valuable units
    attacks_king_zone: bool = False  # lands adjacent to the enemy king
    king_move: bool = False
    material_swing: int = 0          # static eval delta for the mover (cp)


_CENTER = {27, 28, 35, 36}                 # d5 e5 d4 e4 (engine indices)
_EXT_CENTER = _CENTER | {18, 19, 20, 21, 26, 29, 34, 37, 42, 43, 44, 45}


def _king_zone(board, color: str):
    """Squares adjacent to `color`'s king (the squares an attacker wants)."""
    ksq = find_king(board, color)
    if ksq < 0:
        return set()
    r, c = ksq >> 3, ksq & 7
    zone = set()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                zone.add(nr * 8 + nc)
    return zone


def _attacks_from(board, sq: int, piece: str):
    """Squares the `piece` standing on `sq` attacks (sliders blocked by pieces)."""
    from engine import KNIGHT_D, KING_D, ROOK_D, BISHOP_D
    r, c = sq >> 3, sq & 7
    kind = piece[1]
    out = []
    if kind == "N":
        for dr, dc in KNIGHT_D:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                out.append(nr * 8 + nc)
    elif kind == "K":
        for dr, dc in KING_D:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                out.append(nr * 8 + nc)
    elif kind == "P":
        d = -1 if piece[0] == "w" else 1
        for dc in (-1, 1):
            nr, nc = r + d, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                out.append(nr * 8 + nc)
    else:
        dirs = ROOK_D if kind == "R" else BISHOP_D if kind == "B" else KING_D
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                t = nr * 8 + nc
                out.append(t)
                if board[t]:
                    break
                nr += dr
                nc += dc
    return out


def _static_eval_for(state: State, color: str) -> int:
    """Engine static eval expressed from `color`'s point of view (centipawns)."""
    ev = engine.evaluate(state)            # from side-to-move's perspective
    return ev if state.turn == color else -ev


def _least_valuable_attacker(board, target_sq: int, side: str):
    """The cheapest `side` piece that attacks `target_sq` on the given board.

    Returns ``(index, piece)`` or ``None``. Recomputed against the live board so
    that emptied origin squares expose x-ray attackers behind them.
    """
    best = None
    for idx in range(64):
        p = board[idx]
        if not p or p[0] != side or idx == target_sq:
            continue
        if target_sq in _attacks_from(board, idx, p):
            if best is None or VAL[p[1]] < VAL[best[1][1]]:
                best = (idx, p)
    return best


def see_capture(board, target_sq: int, side: str) -> int:
    """Static Exchange Evaluation: material `side` wins by capturing on `target_sq`.

    Plays out the capture sequence with the least-valuable attacker each ply,
    then minimaxes the gain list. The first capture is forced (it is the move
    being evaluated); every recapture afterwards is optional — a side only
    continues if it gains. Used to tell a genuine sacrifice (material left
    hanging for >= a pawn) from an ordinary, safely-defended capture.
    """
    occupant = board[target_sq]
    if occupant is None:
        return 0
    b = list(board)
    gain: list[int] = []
    stm = side
    on_square = VAL[occupant[1]]            # value of the piece to be captured next
    while True:
        atk = _least_valuable_attacker(b, target_sq, stm)
        if atk is None:
            break
        idx, piece = atk
        gain.append(on_square)              # this side captures what sits there
        on_square = VAL[piece[1]]           # its piece now occupies the square
        b[idx] = None                       # attacker leaves its origin (x-ray)
        b[target_sq] = piece
        stm = opp(stm)

    score = 0
    for i in range(len(gain) - 1, -1, -1):
        if i == 0:
            score = gain[i] - score          # forced first capture
        else:
            score = max(0, gain[i] - score)  # later recaptures are optional
    return score


def extract_features(state: State, move: Move, want_san: bool = True) -> MoveFeatures:
    """Compute :class:`MoveFeatures` for `move` legal in `state`.

    `state` is left untouched (the move is made and unmade internally).
    `want_san=False` skips SAN rendering (a full legal-move scan) for bulk
    analysis where only the feature flags matter.
    """
    board = state.board
    mover = move.piece[0]
    f = MoveFeatures(mover=mover)

    f.san = engine.to_san(state, move) if want_san else move.uci()
    f.is_castle = move.flag in ("castleK", "castleQ")
    f.is_promotion = bool(move.promo)
    f.is_pawn_push = move.piece[1] == "P"
    f.king_move = move.piece[1] == "K" and not f.is_castle
    f.central = move.to in _EXT_CENTER

    target = board[move.to]
    if move.flag == "ep":
        f.is_capture = True
        f.captured_value = VAL["P"]
    elif target is not None:
        f.is_capture = True
        f.captured_value = VAL[target[1]]

    # minor-piece development off the back rank
    back_rank = 56 if mover == "w" else 0
    if move.piece[1] in ("N", "B") and (move.frm >> 3) == (back_rank >> 3):
        f.develops_piece = True

    # advancing into the opponent's half
    to_rank = move.to >> 3
    if mover == "w":
        f.advances_into_enemy = to_rank <= 3
    else:
        f.advances_into_enemy = to_rank >= 4

    eval_before = _static_eval_for(state, mover)
    undo = make_move(state, move)
    try:
        enemy = opp(mover)
        f.is_check = in_check(state, enemy)
        over, winner, text = engine.game_status(state)
        f.gives_mate = over and text == "Checkmate"
        eval_after = _static_eval_for(state, mover)
        f.material_swing = eval_after - eval_before

        # king-zone pressure: does the moved piece now attack a square next to
        # the enemy king?
        zone = _king_zone(state.board, enemy)
        landed = _attacks_from(state.board, move.to, state.board[move.to]) \
            if state.board[move.to] else []
        if zone & set(landed):
            f.attacks_king_zone = True

        # fork: the piece now attacks two or more enemy pieces worth a knight+
        valuable_hits = 0
        for t in landed:
            tp = state.board[t]
            if tp and tp[0] == enemy and VAL[tp[1]] >= VAL["N"]:
                valuable_hits += 1
        f.creates_fork = valuable_hits >= 2

        # sacrifice: after the move the opponent can win >= a pawn of material
        # by capturing the piece just moved (Static Exchange Evaluation on the
        # destination square). This catches true offers — a piece left en prise
        # for attacking compensation — which a single-ply material count misses
        # because the loss only lands once the opponent recaptures. Mating moves
        # are excluded (a forced mate is not "giving up" material).
        f.is_sacrifice = (not f.gives_mate) and \
            see_capture(state.board, move.to, enemy) >= 120
    finally:
        unmake_move(state, move, undo)
    return f
