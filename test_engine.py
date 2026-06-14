"""Validation suite: perft (known-correct move counts), the RAG knowledge
base corpus, AI move legality per difficulty, and a mate-in-1 tactic test.

Run:  python test_engine.py
"""

import time
from engine import (State, from_fen, legal_moves, make_move, perft,
                    search_best_move, parse_san, sq_name)
from knowledge import KnowledgeBase

ok = True


def check(label, condition):
    global ok
    ok = ok and condition
    print(f'{label}  {"PASS" if condition else "FAIL"}')


# --- perft from the start position (known values: 20, 400, 8902, 197281) ---
expected = [20, 400, 8902]
s = State()
for d in range(1, 4):
    t = time.time()
    n = perft(s, d)
    check(f'perft({d}) = {n} (expected {expected[d-1]}) [{time.time()-t:.2f}s]',
          n == expected[d - 1])

# --- Kiwipete: stresses castling, en passant, promotions, pins ---
kiwi_fen = 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq -'
kiwi_expected = [48, 2039, 97862]
for d in range(1, 4):
    t = time.time()
    n = perft(from_fen(kiwi_fen), d)
    check(f'kiwipete perft({d}) = {n} (expected {kiwi_expected[d-1]}) [{time.time()-t:.2f}s]',
          n == kiwi_expected[d - 1])

# --- RAG knowledge base: every corpus game/line must replay legally ---
kb = KnowledgeBase()
for err in kb.errors:
    print('  corpus error:', err)
check(f'knowledge base: {kb.size} indexed (position, move) pairs, '
      f'{len(kb.errors)} corpus errors', kb.size > 100 and not kb.errors)

# book must retrieve from the start position
start_book = kb.retrieve(State())
check(f'book retrieval at start position: '
      f'{[bm.san for bm in start_book]}', len(start_book) >= 2)

# --- AI returns a legal move at every difficulty ---
for level in ('easy', 'medium', 'hard'):
    t = time.time()
    m, score, nodes = search_best_move(State(), level)
    legal = any(x.frm == m.frm and x.to == m.to for x in legal_moves(State()))
    check(f'AI({level}) -> {m.uci()}, {nodes:,} nodes [{time.time()-t:.2f}s]', legal)

# --- hard AI must find mate in 1 (scholar's-mate pattern: Qxf7#) ---
s = State()
for san in ('e4', 'e5', 'Bc4', 'Nc6', 'Qh5', 'Nf6'):
    make_move(s, parse_san(s, san))
m, score, nodes = search_best_move(s, 'hard')
check(f'mate-in-1: hard AI played {sq_name(m.frm)}{sq_name(m.to)}',
      sq_name(m.frm) == 'h5' and sq_name(m.to) == 'f7')

print('\nALL TESTS PASSED' if ok else '\nTESTS FAILED')
raise SystemExit(0 if ok else 1)
