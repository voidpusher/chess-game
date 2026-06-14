"""Chess engine: board representation, move generation, evaluation and search.

Board layout: a flat list of 64 squares, index 0 = a8 ... 63 = h1.
Pieces are two-character strings like 'wP', 'bK'; empty squares are None.
"""

import random

FILES = 'abcdefgh'
VAL = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 20000}
MATE = 100_000
INF = float('inf')

# castling-rights bitmask
CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ = 1, 2, 4, 8

KNIGHT_D = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
ROOK_D = ((-1, 0), (1, 0), (0, -1), (0, 1))
BISHOP_D = ((-1, -1), (-1, 1), (1, -1), (1, 1))
KING_D = ROOK_D + BISHOP_D

# Piece-square tables from White's perspective; index 0 = a8 (black's back rank).
PST = {
    'P': (0, 0, 0, 0, 0, 0, 0, 0,
          50, 50, 50, 50, 50, 50, 50, 50,
          10, 10, 20, 30, 30, 20, 10, 10,
          5, 5, 10, 25, 25, 10, 5, 5,
          0, 0, 0, 20, 20, 0, 0, 0,
          5, -5, -10, 0, 0, -10, -5, 5,
          5, 10, 10, -20, -20, 10, 10, 5,
          0, 0, 0, 0, 0, 0, 0, 0),
    'N': (-50, -40, -30, -30, -30, -30, -40, -50,
          -40, -20, 0, 0, 0, 0, -20, -40,
          -30, 0, 10, 15, 15, 10, 0, -30,
          -30, 5, 15, 20, 20, 15, 5, -30,
          -30, 0, 15, 20, 20, 15, 0, -30,
          -30, 5, 10, 15, 15, 10, 5, -30,
          -40, -20, 0, 5, 5, 0, -20, -40,
          -50, -40, -30, -30, -30, -30, -40, -50),
    'B': (-20, -10, -10, -10, -10, -10, -10, -20,
          -10, 0, 0, 0, 0, 0, 0, -10,
          -10, 0, 5, 10, 10, 5, 0, -10,
          -10, 5, 5, 10, 10, 5, 5, -10,
          -10, 0, 10, 10, 10, 10, 0, -10,
          -10, 10, 10, 10, 10, 10, 10, -10,
          -10, 5, 0, 0, 0, 0, 5, -10,
          -20, -10, -10, -10, -10, -10, -10, -20),
    'R': (0, 0, 0, 0, 0, 0, 0, 0,
          5, 10, 10, 10, 10, 10, 10, 5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          0, 0, 0, 5, 5, 0, 0, 0),
    'Q': (-20, -10, -10, -5, -5, -10, -10, -20,
          -10, 0, 0, 0, 0, 0, 0, -10,
          -10, 0, 5, 5, 5, 5, 0, -10,
          -5, 0, 5, 5, 5, 5, 0, -5,
          0, 0, 5, 5, 5, 5, 0, -5,
          -10, 5, 5, 5, 5, 5, 0, -10,
          -10, 0, 5, 0, 0, 0, 0, -10,
          -20, -10, -10, -5, -5, -10, -10, -20),
    'K': (-30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30,
          -20, -30, -30, -40, -40, -30, -30, -20,
          -10, -20, -20, -20, -20, -20, -20, -10,
          20, 20, 0, 0, 0, 0, 20, 20,
          20, 30, 10, 0, 0, 10, 30, 20),
}


def opp(color):
    return 'b' if color == 'w' else 'w'


def sq_name(i):
    return FILES[i & 7] + str(8 - (i >> 3))


def sq_index(name):
    return FILES.index(name[0]) + (8 - int(name[1])) * 8


class Move:
    __slots__ = ('frm', 'to', 'piece', 'promo', 'flag', 'sort_key')

    def __init__(self, frm, to, piece, promo=None, flag=None):
        self.frm = frm
        self.to = to
        self.piece = piece
        self.promo = promo
        self.flag = flag  # None | 'double' | 'ep' | 'castleK' | 'castleQ'
        self.sort_key = 0

    def uci(self):
        return sq_name(self.frm) + sq_name(self.to) + (self.promo.lower() if self.promo else '')

    def __repr__(self):
        return f'Move({self.uci()})'


class State:
    __slots__ = ('board', 'turn', 'castling', 'ep', 'halfmove')

    def __init__(self):
        back = ('R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R')
        b = [None] * 64
        for c in range(8):
            b[c] = 'b' + back[c]
            b[8 + c] = 'bP'
            b[48 + c] = 'wP'
            b[56 + c] = 'w' + back[c]
        self.board = b
        self.turn = 'w'
        self.castling = CASTLE_WK | CASTLE_WQ | CASTLE_BK | CASTLE_BQ
        self.ep = -1
        self.halfmove = 0

    def key(self):
        """Hashable position identity — used by the RAG retrieval index."""
        return (tuple(self.board), self.turn, self.castling, self.ep)


def from_fen(fen):
    placement, turn, castle, ep = fen.split()[:4]
    s = State()
    s.board = [None] * 64
    i = 0
    for ch in placement:
        if ch == '/':
            continue
        if ch.isdigit():
            i += int(ch)
        else:
            s.board[i] = ('w' if ch.isupper() else 'b') + ch.upper()
            i += 1
    s.turn = turn
    s.castling = ((CASTLE_WK if 'K' in castle else 0) | (CASTLE_WQ if 'Q' in castle else 0) |
                  (CASTLE_BK if 'k' in castle else 0) | (CASTLE_BQ if 'q' in castle else 0))
    s.ep = -1 if ep == '-' else sq_index(ep)
    s.halfmove = 0
    return s


def is_attacked(board, sq, by):
    r, c = sq >> 3, sq & 7
    for dr, dc in KNIGHT_D:
        nr, nc = r + dr, c + dc
        if 0 <= nr < 8 and 0 <= nc < 8 and board[nr * 8 + nc] == by + 'N':
            return True
    for dr, dc in KING_D:
        nr, nc = r + dr, c + dc
        if 0 <= nr < 8 and 0 <= nc < 8 and board[nr * 8 + nc] == by + 'K':
            return True
    pr = r + 1 if by == 'w' else r - 1  # rank the attacking pawn stands on
    if 0 <= pr < 8:
        for dc in (-1, 1):
            nc = c + dc
            if 0 <= nc < 8 and board[pr * 8 + nc] == by + 'P':
                return True
    for dr, dc in ROOK_D:
        nr, nc = r + dr, c + dc
        while 0 <= nr < 8 and 0 <= nc < 8:
            p = board[nr * 8 + nc]
            if p:
                if p[0] == by and p[1] in 'RQ':
                    return True
                break
            nr += dr
            nc += dc
    for dr, dc in BISHOP_D:
        nr, nc = r + dr, c + dc
        while 0 <= nr < 8 and 0 <= nc < 8:
            p = board[nr * 8 + nc]
            if p:
                if p[0] == by and p[1] in 'BQ':
                    return True
                break
            nr += dr
            nc += dc
    return False


def find_king(board, color):
    target = color + 'K'
    for i in range(64):
        if board[i] == target:
            return i
    return -1


def in_check(state, color):
    return is_attacked(state.board, find_king(state.board, color), opp(color))


def pseudo_moves(state, captures_only=False):
    b = state.board
    color = state.turn
    moves = []
    direction = -1 if color == 'w' else 1
    start_row = 6 if color == 'w' else 1
    promo_row = 0 if color == 'w' else 7

    def push(frm, to, piece, flag=None):
        if piece[1] == 'P' and (to >> 3) == promo_row:
            for promo in ('Q', 'R', 'B', 'N'):
                moves.append(Move(frm, to, piece, promo, flag))
        else:
            moves.append(Move(frm, to, piece, None, flag))

    for i in range(64):
        p = b[i]
        if not p or p[0] != color:
            continue
        r, c = i >> 3, i & 7
        kind = p[1]

        if kind == 'P':
            nr = r + direction
            if 0 <= nr < 8:
                fwd = nr * 8 + c
                if not b[fwd] and (not captures_only or nr == promo_row):
                    push(i, fwd, p)
                if not b[fwd] and r == start_row and not captures_only:
                    fwd2 = (r + 2 * direction) * 8 + c
                    if not b[fwd2]:
                        moves.append(Move(i, fwd2, p, None, 'double'))
                for dc in (-1, 1):
                    nc = c + dc
                    if 0 <= nc < 8:
                        t = nr * 8 + nc
                        if b[t] and b[t][0] != color:
                            push(i, t, p)
                        elif t == state.ep and not b[t]:
                            moves.append(Move(i, t, p, None, 'ep'))
        elif kind == 'N':
            for dr, dc in KNIGHT_D:
                nr, nc = r + dr, c + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    t = nr * 8 + nc
                    if b[t]:
                        if b[t][0] != color:
                            push(i, t, p)
                    elif not captures_only:
                        push(i, t, p)
        elif kind == 'K':
            for dr, dc in KING_D:
                nr, nc = r + dr, c + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    t = nr * 8 + nc
                    if b[t]:
                        if b[t][0] != color:
                            push(i, t, p)
                    elif not captures_only:
                        push(i, t, p)
        else:
            dirs = ROOK_D if kind == 'R' else BISHOP_D if kind == 'B' else KING_D
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                while 0 <= nr < 8 and 0 <= nc < 8:
                    t = nr * 8 + nc
                    if b[t]:
                        if b[t][0] != color:
                            push(i, t, p)
                        break
                    if not captures_only:
                        push(i, t, p)
                    nr += dr
                    nc += dc

    if not captures_only:
        enemy = opp(color)
        if color == 'w' and b[60] == 'wK' and not is_attacked(b, 60, enemy):
            if (state.castling & CASTLE_WK and b[63] == 'wR' and not b[61] and not b[62]
                    and not is_attacked(b, 61, enemy) and not is_attacked(b, 62, enemy)):
                moves.append(Move(60, 62, 'wK', None, 'castleK'))
            if (state.castling & CASTLE_WQ and b[56] == 'wR' and not b[57] and not b[58] and not b[59]
                    and not is_attacked(b, 59, enemy) and not is_attacked(b, 58, enemy)):
                moves.append(Move(60, 58, 'wK', None, 'castleQ'))
        if color == 'b' and b[4] == 'bK' and not is_attacked(b, 4, enemy):
            if (state.castling & CASTLE_BK and b[7] == 'bR' and not b[5] and not b[6]
                    and not is_attacked(b, 5, enemy) and not is_attacked(b, 6, enemy)):
                moves.append(Move(4, 6, 'bK', None, 'castleK'))
            if (state.castling & CASTLE_BQ and b[0] == 'bR' and not b[1] and not b[2] and not b[3]
                    and not is_attacked(b, 3, enemy) and not is_attacked(b, 2, enemy)):
                moves.append(Move(4, 2, 'bK', None, 'castleQ'))
    return moves


# rights cleared when a move touches these squares
_RIGHTS_MASK = {63: ~CASTLE_WK, 56: ~CASTLE_WQ, 7: ~CASTLE_BK, 0: ~CASTLE_BQ}


def make_move(state, m):
    b = state.board
    color = m.piece[0]
    undo = (b[m.to], state.castling, state.ep, state.halfmove, None)
    captured = b[m.to]
    b[m.to] = color + m.promo if m.promo else m.piece
    b[m.frm] = None
    state.ep = -1
    if m.flag == 'double':
        state.ep = (m.frm + m.to) // 2
    elif m.flag == 'ep':
        cap_sq = m.to + (8 if color == 'w' else -8)
        undo = (undo[0], undo[1], undo[2], undo[3], b[cap_sq])
        b[cap_sq] = None
    elif m.flag == 'castleK':
        if color == 'w':
            b[61], b[63] = b[63], None
        else:
            b[5], b[7] = b[7], None
    elif m.flag == 'castleQ':
        if color == 'w':
            b[59], b[56] = b[56], None
        else:
            b[3], b[0] = b[0], None
    if m.piece == 'wK':
        state.castling &= ~(CASTLE_WK | CASTLE_WQ)
    elif m.piece == 'bK':
        state.castling &= ~(CASTLE_BK | CASTLE_BQ)
    for sq in (m.frm, m.to):
        mask = _RIGHTS_MASK.get(sq)
        if mask is not None:
            state.castling &= mask
    state.halfmove = 0 if (m.piece[1] == 'P' or captured) else state.halfmove + 1
    state.turn = opp(state.turn)
    return undo


def unmake_move(state, m, undo):
    b = state.board
    color = m.piece[0]
    b[m.frm] = m.piece
    b[m.to] = undo[0]
    if m.flag == 'ep':
        cap_sq = m.to + (8 if color == 'w' else -8)
        b[cap_sq] = undo[4]
    elif m.flag == 'castleK':
        if color == 'w':
            b[63], b[61] = b[61], None
        else:
            b[7], b[5] = b[5], None
    elif m.flag == 'castleQ':
        if color == 'w':
            b[56], b[59] = b[59], None
        else:
            b[0], b[3] = b[3], None
    state.castling = undo[1]
    state.ep = undo[2]
    state.halfmove = undo[3]
    state.turn = opp(state.turn)


def legal_moves(state):
    color = state.turn
    out = []
    for m in pseudo_moves(state):
        undo = make_move(state, m)
        if not in_check(state, color):
            out.append(m)
        unmake_move(state, m, undo)
    return out


def evaluate(state):
    """Static evaluation from the side-to-move's perspective (centipawns)."""
    score = 0
    board = state.board
    for i in range(64):
        p = board[i]
        if not p:
            continue
        kind = p[1]
        if p[0] == 'w':
            score += VAL[kind] + PST[kind][i]
        else:
            score -= VAL[kind] + PST[kind][i ^ 56]
    return score if state.turn == 'w' else -score


def order_moves(state, moves):
    board = state.board
    for m in moves:
        s = 0
        cap = board[m.to]
        if cap:
            s += 10 * VAL[cap[1]] - VAL[m.piece[1]]
        if m.flag == 'ep':
            s += 10 * VAL['P']
        if m.promo:
            s += 10 * VAL[m.promo]
        m.sort_key = s
    moves.sort(key=lambda m: m.sort_key, reverse=True)


_nodes = 0


def quiesce(state, alpha, beta, depth):
    global _nodes
    _nodes += 1
    stand = evaluate(state)
    if stand >= beta:
        return beta
    if stand > alpha:
        alpha = stand
    if depth == 0:
        return alpha
    color = state.turn
    moves = pseudo_moves(state, captures_only=True)
    order_moves(state, moves)
    for m in moves:
        undo = make_move(state, m)
        if in_check(state, color):
            unmake_move(state, m, undo)
            continue
        score = -quiesce(state, -beta, -alpha, depth - 1)
        unmake_move(state, m, undo)
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
    return alpha


def negamax(state, depth, alpha, beta, ply, use_quiesce):
    global _nodes
    _nodes += 1
    if state.halfmove >= 100:
        return 0
    if depth == 0:
        return quiesce(state, alpha, beta, 6) if use_quiesce else evaluate(state)
    color = state.turn
    moves = pseudo_moves(state)
    order_moves(state, moves)
    best = -INF
    any_legal = False
    for m in moves:
        undo = make_move(state, m)
        if in_check(state, color):
            unmake_move(state, m, undo)
            continue
        any_legal = True
        score = -negamax(state, depth - 1, -beta, -alpha, ply + 1, use_quiesce)
        unmake_move(state, m, undo)
        if score > best:
            best = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break
    if not any_legal:
        return -(MATE - ply) if in_check(state, color) else 0
    return best


# difficulty -> (search depth, random noise in centipawns, quiescence search)
DIFFICULTY = {
    'easy': (1, 150, False),
    'medium': (2, 0, True),
    'hard': (3, 0, True),
}


def search_best_move(state, level):
    """Alpha-beta search. Returns (move, score_cp, nodes) or (None, 0, 0)."""
    global _nodes
    depth, noise, use_quiesce = DIFFICULTY[level]
    moves = legal_moves(state)
    if not moves:
        return None, 0, 0
    order_moves(state, moves)
    _nodes = 0
    best_score = -INF
    best_moves = []
    for m in moves:
        undo = make_move(state, m)
        # Child window (-INF, -best+1): ties and improvements come back exact,
        # worse moves may return bounds (which we discard anyway). With noise
        # enabled scores must all be exact, so search the full window.
        beta = INF if (noise or best_score == -INF) else -best_score + 1
        score = -negamax(state, depth - 1, -INF, beta, 1, use_quiesce)
        unmake_move(state, m, undo)
        if noise:
            score += random.uniform(-noise, noise)
        if score > best_score + 1e-9:
            best_score = score
            best_moves = [m]
        elif abs(score - best_score) <= 1e-9:
            best_moves.append(m)
    return random.choice(best_moves), best_score, _nodes


def game_status(state):
    """Returns (over, winner, text). winner is 'w'/'b'/None."""
    if not legal_moves(state):
        if in_check(state, state.turn):
            return True, opp(state.turn), 'Checkmate'
        return True, None, 'Stalemate — draw'
    if state.halfmove >= 100:
        return True, None, 'Draw — 50-move rule'
    minors = 0
    for p in state.board:
        if not p or p[1] == 'K':
            continue
        if p[1] in 'PRQ':
            return False, None, ''
        minors += 1
    if minors <= 1:
        return True, None, 'Draw — insufficient material'
    return False, None, ''


def to_san(state, m):
    """Standard algebraic notation for a legal move in the current position."""
    if m.flag == 'castleK':
        base = 'O-O'
    elif m.flag == 'castleQ':
        base = 'O-O-O'
    else:
        kind = m.piece[1]
        capture = bool(state.board[m.to]) or m.flag == 'ep'
        if kind == 'P':
            base = (FILES[m.frm & 7] + 'x' if capture else '') + sq_name(m.to)
            if m.promo:
                base += '=' + m.promo
        else:
            others = [o for o in legal_moves(state)
                      if o.piece == m.piece and o.to == m.to and o.frm != m.frm]
            disamb = ''
            if others:
                same_file = any((o.frm & 7) == (m.frm & 7) for o in others)
                same_rank = any((o.frm >> 3) == (m.frm >> 3) for o in others)
                if not same_file:
                    disamb = FILES[m.frm & 7]
                elif not same_rank:
                    disamb = str(8 - (m.frm >> 3))
                else:
                    disamb = sq_name(m.frm)
            base = kind + disamb + ('x' if capture else '') + sq_name(m.to)
    undo = make_move(state, m)
    over, _, text = game_status(state)
    if over and text == 'Checkmate':
        base += '#'
    elif in_check(state, state.turn):
        base += '+'
    unmake_move(state, m, undo)
    return base


def parse_san(state, token):
    """Find the legal move matching a SAN token (e.g. 'Nf3', 'exd5', 'O-O', 'e8=Q+')."""
    cleaned = token.replace('0', 'O').rstrip('+#!?').replace('e.p.', '')
    for m in legal_moves(state):
        if to_san(state, m).rstrip('+#') == cleaned:
            return m
    return None


def perft(state, depth):
    if depth == 0:
        return 1
    n = 0
    for m in legal_moves(state):
        undo = make_move(state, m)
        n += perft(state, depth - 1)
        unmake_move(state, m, undo)
    return n
