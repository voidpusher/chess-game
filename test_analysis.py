"""Tests for the game-analysis module.

Scenario A: human plays Black and walks into Scholar's Mate — the losing move
            (3... Nf6??) must be flagged as a blunder.
Scenario B: human plays White, reaches a mate-in-1 and retreats the queen
            instead — analysis must report the missed forced mate.
"""

import sys
from engine import State, make_move, parse_san
from analysis import analyze_game
from knowledge import KnowledgeBase

kb = KnowledgeBase()
ok = True


def check(label, condition):
    global ok
    ok = ok and condition
    print(f'{label}  {"PASS" if condition else "FAIL"}')


def build(sans):
    state = State()
    moves = []
    for san in sans:
        m = parse_san(state, san)
        assert m is not None, f'bad SAN in test: {san}'
        moves.append((m, san))
        make_move(state, m)
    return moves


# --- Scenario A: human is Black, blunders into Scholar's Mate -------------
moves = build(['e4', 'e5', 'Bc4', 'Nc6', 'Qh5', 'Nf6', 'Qxf7#'])
report = analyze_game(moves, 'b', kb)
entries = report['entries']
check(f'A: analyzed {len(entries)} black moves (expected 3)', len(entries) == 3)
nf6 = entries[2]
check(f'A: 3... Nf6 classified "{nf6["kind"]}" (expected blunder)',
      nf6['kind'] == 'blunder')
check(f'A: blunder comment mentions the punishment: "{nf6["comment"]}"',
      'Qxf7' in nf6['comment'] or 'mate' in nf6['comment'].lower())
check(f'A: accuracy {report["summary"]["accuracy"]:.1f}% in range',
      0 <= report['summary']['accuracy'] <= 100)
check(f'A: graph has one point per human move', len(report['graph']) == 3)
check(f'A: coaching advice generated ({len(report["summary"]["advice"])} tips)',
      len(report['summary']['advice']) >= 1)

# --- Scenario B: human is White, misses mate-in-1 -------------------------
moves = build(['e4', 'e5', 'Bc4', 'Nc6', 'Qh5', 'Nf6', 'Qd1'])
report = analyze_game(moves, 'w', kb)
entries = report['entries']
qd1 = entries[-1]
check(f'B: 4. Qd1 flagged as missed mate (kind={qd1["kind"]})',
      qd1['missed_mate'] and qd1['kind'] in ('mistake', 'blunder'))
check(f'B: comment names the mating move: "{qd1["comment"]}"',
      'Qxf7' in qd1['comment'])
book_moves = [e for e in entries if e['kind'] == 'book']
check(f'B: opening theory recognised ({len(book_moves)} book moves)',
      len(book_moves) >= 1)

print('\nALL ANALYSIS TESTS PASSED' if ok else '\nANALYSIS TESTS FAILED')
sys.exit(0 if ok else 1)
