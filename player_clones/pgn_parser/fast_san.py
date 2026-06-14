"""Fast SAN -> Move matching for bulk PGN replay.

`engine.parse_san` renders the SAN string of *every* legal move at *every*
position to find a match — perfectly fine for interactive use, far too slow for
replaying thousands of games (it made a full-history import take ~an hour).

This module parses the SAN token directly (piece kind, destination square,
origin disambiguation, promotion) and filters the legal-move list on those
fields — no SAN rendering at all. When the filter is not unique (malformed or
under-disambiguated input), it falls back to `engine.parse_san` so behaviour is
never *less* correct than the original.

`engine.py` itself is untouched.
"""

from __future__ import annotations

import re

import engine
from engine import State, Move, legal_moves, sq_index

# Qbd7, R1e2, exd5, e8=Q+, Nf3!?, dxe6e.p. ...
_SAN_RE = re.compile(
    r"^([KQRBN])?"          # 1 piece (pawn if absent)
    r"([a-h])?([1-8])?"     # 2,3 origin disambiguation
    r"(x)?"                 # 4 capture marker
    r"([a-h][1-8])"         # 5 destination
    r"(?:=?([QRBN]))?$"     # 6 promotion piece
)


def match_san(state: State, token: str) -> Move | None:
    """Find the legal move written as `token` in `state` (or None)."""
    cleaned = token.replace("0", "O").rstrip("+#!?")
    if cleaned.endswith("e.p."):
        cleaned = cleaned[:-4]

    moves = legal_moves(state)

    if cleaned in ("O-O", "O-O-O"):
        flag = "castleK" if cleaned == "O-O" else "castleQ"
        for m in moves:
            if m.flag == flag:
                return m
        return None

    g = _SAN_RE.match(cleaned)
    if not g:
        return engine.parse_san(state, token)     # weird token — old slow path

    kind = g.group(1) or "P"
    from_file = g.group(2)
    from_rank = g.group(3)
    to_sq = sq_index(g.group(5))
    promo = g.group(6)

    cand = []
    for m in moves:
        if m.to != to_sq or m.piece[1] != kind:
            continue
        if promo and m.promo != promo:
            continue
        if not promo and m.promo:
            continue
        if from_file and (m.frm & 7) != "abcdefgh".index(from_file):
            continue
        if from_rank and (m.frm >> 3) != 8 - int(from_rank):
            continue
        cand.append(m)

    if len(cand) == 1:
        return cand[0]
    if not cand:
        return None
    # ambiguous after filtering (shouldn't happen with well-formed PGN) —
    # let the reference implementation decide
    return engine.parse_san(state, token)
