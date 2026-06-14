"""RAG (Retrieval-Augmented Generation) layer for the chess AI.

The corpus below contains real grandmaster games and mainline opening theory.
At build time every game is replayed move by move and indexed by *position*
(not by move sequence), so transpositions retrieve correctly.

At play time the AI:
  1. RETRIEVES  - looks up the current position in the index,
  2. AUGMENTS   - merges the retrieved book moves / sources with its own search,
  3. GENERATES  - picks a move and produces commentary citing the sources
                  the move was retrieved from.
"""

import random
from engine import State, make_move, parse_san, to_san

# ---------------------------------------------------------------------------
# Corpus 1: famous master games (full game scores)
# ---------------------------------------------------------------------------
FAMOUS_GAMES = [
    {
        'name': 'The Opera Game',
        'white': 'Paul Morphy', 'black': 'Duke Karl & Count Isouard', 'year': 1858,
        'winner': 'w',
        'moves': 'e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 '
                 'Nc3 c6 Bg5 b5 Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 Rxd7 Rxd7 '
                 'Rd1 Qe6 Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#',
    },
    {
        'name': 'The Immortal Game',
        'white': 'Adolf Anderssen', 'black': 'Lionel Kieseritzky', 'year': 1851,
        'winner': 'w',
        'moves': 'e4 e5 f4 exf4 Bc4 Qh4+ Kf1 b5 Bxb5 Nf6 Nf3 Qh6 d3 Nh5 '
                 'Nh4 Qg5 Nf5 c6 g4 Nf6 Rg1 cxb5 h4 Qg6 h5 Qg5 Qf3 Ng8 '
                 'Bxf4 Qf6 Nc3 Bc5 Nd5 Qxb2 Bd6 Bxg1 e5 Qxa1+ Ke2 Na6 '
                 'Nxg7+ Kd8 Qf6+ Nxf6 Be7#',
    },
    {
        'name': "Legal's Mate",
        'white': 'Kermur de Legal', 'black': 'Saint Brie', 'year': 1750,
        'winner': 'w',
        'moves': 'e4 e5 Bc4 d6 Nf3 Bg4 Nc3 g6 Nxe5 Bxd1 Bxf7+ Ke7 Nd5#',
    },
    {
        'name': "Scholar's Mate (trap)",
        'white': 'classic trap', 'black': '', 'year': 0,
        'winner': 'w',
        'moves': 'e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#',
    },
    {
        # A Samay-flavoured queen-raid miniature (Caro-Kann), great for showing
        # how a tempo-grabbing attacker punishes a greedy queen.
        'name': 'Réti vs Tartakower (Caro-Kann miniature)',
        'white': 'Richard Réti', 'black': 'Savielly Tartakower', 'year': 1910,
        'winner': 'w',
        'moves': 'e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6 Qd3 e5 dxe5 Qa5+ Bd2 Qxe5 '
                 'O-O-O Nxe4 Qd8+ Kxd8 Bg5+ Ke8 Rd8#',
    },
    {
        # Englund Gambit trap — exactly the kind of cheeky Black gambit Samay
        # springs on stream when his opponent plays 1.d4.
        'name': 'Englund Gambit Trap (Black mates)',
        'white': 'unwary d4 player', 'black': 'gambiteer', 'year': 0,
        'winner': 'b',
        'moves': 'd4 e5 dxe5 Nc6 Nf3 Qe7 Bf4 Qb4+ Bd2 Qxb2 Bc3 Bb4 Qd2 Bxc3 '
                 'Qxc3 Qc1#',
    },
]

# ---------------------------------------------------------------------------
# Corpus 2: mainline opening theory
# ---------------------------------------------------------------------------
OPENING_LINES = [
    ('Italian Game — Giuoco Piano', 'e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O'),
    ('Ruy Lopez — Closed Morphy Defence', 'e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O'),
    ('Scotch Game — Mieses Variation', 'e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nxc6 bxc6 e5 Qe7 Qe2 Nd5'),
    ('Vienna Game — Falkbeer Variation', 'e4 e5 Nc3 Nf6 f4 d5 fxe5 Nxe4'),
    ('Sicilian Defence — Najdorf', 'e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6'),
    ('Sicilian Defence — Dragon', 'e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6'),
    ('French Defence — Classical', 'e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7'),
    ('Caro-Kann — Classical', 'e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5'),
    ('Scandinavian Defence', 'e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 c6'),
    ("Queen's Gambit Declined — Orthodox", 'd4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7'),
    ("Queen's Gambit Accepted", 'd4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5'),
    ('Slav Defence — Main Line', 'd4 d5 c4 c6 Nf3 Nf6 Nc3 dxc4 a4 Bf5'),
    ("King's Indian Defence — Classical", 'd4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5'),
    ('Nimzo-Indian Defence — Rubinstein', 'd4 Nf6 c4 e6 Nc3 Bb4 e3 O-O Bd3 d5'),
    ('London System', 'd4 d5 Nf3 Nf6 Bf4 e6 e3 Bd6 Bg3 O-O'),
    ('English Opening — Four Knights', 'c4 e5 Nc3 Nf6 Nf3 Nc6 g3 d5 cxd5 Nxd5 Bg2 Nb6 O-O Be7'),
    # --- Samay Raina repertoire (research-based) ---------------------------- #
    # As White: King's Gambit (his declared favourite), Italian, London.
    ("King's Gambit Accepted — Kieseritzky", 'e4 e5 f4 exf4 Nf3 g5 Bc4 g4 O-O gxf3 Qxf3'),
    ("King's Gambit Accepted — Bishop's Gambit", 'e4 e5 f4 exf4 Bc4 Qh4+ Kf1 d6'),
    ("Italian Game — Giuoco Pianissimo", 'e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O'),
    ('London System — Samay setup', 'd4 d5 Bf4 Nf6 e3 e6 Nf3 Bd6 Bg3 O-O Bd3'),
    # As Black: Sicilian Dragon vs e4, Englund / KID vs d4.
    ('Sicilian Defence — Dragon Main Line', 'e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O'),
    ('Englund Gambit — Main Trap', 'd4 e5 dxe5 Nc6 Nf3 Qe7 Bf4 Qb4+ Bd2 Qxb2 Bc3 Bb4'),
    ("King's Indian Defence — Samay vs d4", 'd4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5'),
]


class BookMove:
    __slots__ = ('uci', 'san', 'count', 'sources')

    def __init__(self, uci, san):
        self.uci = uci
        self.san = san
        self.count = 0
        self.sources = []  # source labels this move was retrieved from


class KnowledgeBase:
    """Position-keyed retrieval index over the game/opening corpus."""

    def __init__(self):
        self.index = {}   # state.key() -> {uci: BookMove}
        self.errors = []  # corpus entries that failed to replay
        self.size = 0     # number of indexed (position, move) pairs
        for game in FAMOUS_GAMES:
            label = game['name']
            if game['year']:
                label += f" ({game['white']} vs {game['black']}, {game['year']})"
            # index only the WINNER's moves — the loser's moves in these games
            # are exactly the mistakes being punished, not theory to imitate
            self._add_line(label, game['moves'], side=game['winner'])
        for name, moves in OPENING_LINES:
            self._add_line(name, moves)

    def _add_line(self, label, san_moves, side=None):
        state = State()
        for token in san_moves.split():
            move = parse_san(state, token)
            if move is None:
                self.errors.append(f'{label}: could not parse "{token}"')
                return
            if side is None or state.turn == side:
                key = state.key()
                entry = self.index.setdefault(key, {})
                uci = move.uci()
                if uci not in entry:
                    entry[uci] = BookMove(uci, to_san(state, move))
                    self.size += 1
                bm = entry[uci]
                bm.count += 1
                if label not in bm.sources:
                    bm.sources.append(label)
            make_move(state, move)

    def retrieve(self, state):
        """All book moves known for this position, most popular first."""
        entry = self.index.get(state.key())
        if not entry:
            return []
        return sorted(entry.values(), key=lambda bm: bm.count, reverse=True)

    def pick_book_move(self, state, level, move_number):
        """Choose a retrieved move (or None to fall through to the engine).

        easy   - only sometimes remembers its theory,
        medium - follows the book for the first 8 full moves,
        hard   - plays a book move whenever one is retrieved.
        """
        candidates = self.retrieve(state)
        if not candidates:
            return None
        if level == 'easy' and random.random() > 0.4:
            return None
        if level == 'medium' and move_number > 8:
            return None
        weights = [bm.count for bm in candidates]
        return random.choices(candidates, weights=weights)[0]
