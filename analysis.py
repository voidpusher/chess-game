"""Post-game analysis of the human player's moves.

For every move the human played, the engine (depth-3 + quiescence) evaluates:
  - what the best move in the position was,
  - how much the played move cost (centipawn loss),
  - what the opponent's strongest punishment was,
  - whether the move followed opening theory in the RAG knowledge base.

Moves are classified lichess-style (book / best / excellent / good /
inaccuracy / mistake / blunder), an accuracy score is computed, and a set of
human-readable coaching tips is generated from the patterns found.
"""

import math

from engine import (MATE, State, game_status, legal_moves, make_move,
                    search_best_move, to_san)

ANALYSIS_LEVEL = 'hard'

LABELS = {
    'book': ('book', ''),
    'best': ('best move', '!'),
    'excellent': ('excellent', ''),
    'good': ('good', ''),
    'inaccuracy': ('inaccuracy', '?!'),
    'mistake': ('mistake', '?'),
    'blunder': ('blunder', '??'),
}


def _is_mate_score(score):
    return abs(score) > MATE - 1000


def _mate_in(score):
    return (MATE - abs(score) + 1) // 2


def _move_label(ply, san):
    n = ply // 2 + 1
    return f'{n}. {san}' if ply % 2 == 0 else f'{n}... {san}'


def _classify(loss, played_best, in_book):
    if in_book and loss < 100:   # book status never excuses a losing move
        return 'book'
    if played_best:
        return 'best'
    if loss < 20:
        return 'excellent'
    if loss < 50:
        return 'good'
    if loss < 100:
        return 'inaccuracy'
    if loss < 300:
        return 'mistake'
    return 'blunder'


def _move_accuracy(loss):
    return max(0.0, min(100.0, 103.16 * math.exp(-0.04354 * min(loss, 1000)) - 3.17))


def analyze_game(moves, human_color, kb=None, progress=None):
    """moves: list of (Move, san) in game order. Returns a report dict."""
    state = State()
    entries = []
    graph = []          # (full-move number, eval in cp from the human's POV)
    human_plies = 0

    for ply, (m, san) in enumerate(moves):
        if progress:
            progress(ply + 1, len(moves))
        mover = state.turn
        if mover != human_color:
            make_move(state, m)
            continue

        human_plies += 1
        uci = m.uci()
        book_moves = kb.retrieve(state) if kb else []
        in_book = any(bm.uci == uci for bm in book_moves)
        best_m, best_sc, _ = search_best_move(state, ANALYSIS_LEVEL)
        best_san = to_san(state, best_m)
        best_was_capture = state.board[best_m.to] is not None or best_m.flag == 'ep'
        played_best = uci == best_m.uci()

        make_move(state, m)

        reply_san = None
        reply_is_capture = False
        if legal_moves(state):
            reply_m, reply_sc, _ = search_best_move(state, ANALYSIS_LEVEL)
            actual_sc = -reply_sc
            reply_san = to_san(state, reply_m)
            reply_is_capture = (state.board[reply_m.to] is not None
                                or reply_m.flag == 'ep')
        else:
            over, winner, _ = game_status(state)
            actual_sc = MATE - 1 if winner == mover else 0

        loss = 0 if played_best else max(0, best_sc - actual_sc)
        kind = _classify(loss, played_best, in_book)

        # build the comment
        notes = []
        missed_mate = (_is_mate_score(best_sc) and best_sc > 0
                       and not (_is_mate_score(actual_sc) and actual_sc > 0))
        if missed_mate:
            notes.append(f'You missed a forced mate in {_mate_in(best_sc)}: '
                         f'{best_san} was winning.')
        elif kind in ('inaccuracy', 'mistake', 'blunder'):
            better = f'Better was {best_san}'
            if best_was_capture:
                better += ' (a capture you missed)'
            elif best_sc > 150 and actual_sc < 50:
                better += ' (a winning idea)'
            notes.append(better + '.')
            if reply_san and (reply_is_capture or '+' in reply_san or '#' in reply_san):
                notes.append(f'Your move allowed {reply_san}.')
            if _is_mate_score(actual_sc) and actual_sc < 0:
                notes.append(f'This loses by force (mate in {_mate_in(actual_sc)}).')
        elif in_book:
            srcs = [bm for bm in book_moves if bm.uci == uci]
            if srcs and srcs[0].sources:
                notes.append(f'Theory: {srcs[0].sources[0]}.')
        elif played_best:
            notes.append('The engine’s top choice.')

        entries.append({
            'ply': ply, 'san': san, 'label': _move_label(ply, san),
            'kind': kind, 'loss': loss, 'accuracy': _move_accuracy(loss),
            'best_san': best_san, 'reply_san': reply_san,
            'eval_after': actual_sc,        # human's POV
            'in_book': in_book, 'missed_mate': missed_mate,
            'comment': ' '.join(notes),
        })
        graph.append((ply // 2 + 1, max(-800, min(800, actual_sc))))

    summary = _summarize(entries, moves, human_color, human_plies)
    return {'entries': entries, 'summary': summary, 'graph': graph}


def _summarize(entries, moves, human_color, human_plies):
    counts = {k: 0 for k in LABELS}
    total_loss = 0
    for e in entries:
        counts[e['kind']] += 1
        total_loss += e['loss']
    n = len(entries) or 1
    accuracy = sum(e['accuracy'] for e in entries) / n
    avg_loss = total_loss / n

    advice = []

    # opening: where did the player leave theory?
    first_out = next((e for e in entries
                      if not e['in_book'] and e['ply'] < 16), None)
    plies_in_book = sum(1 for e in entries if e['in_book'])
    if first_out is not None and plies_in_book < 3 and first_out['kind'] != 'best':
        advice.append(f'Opening: you left known theory early ({first_out["label"]}). '
                      f'Studying a few mainline openings would give you safer, '
                      f'well-tested positions out of the gate.')
    elif plies_in_book >= 3:
        advice.append(f'Opening: good — you followed established theory for '
                      f'{plies_in_book} moves.')

    # blunders that immediately lost material
    hangs = [e for e in entries if e['kind'] == 'blunder' and e['reply_san']
             and 'x' in e['reply_san']]
    if hangs:
        spots = ', '.join(e['label'] for e in hangs[:3])
        advice.append(f'Hanging pieces: {len(hangs)} of your moves immediately '
                      f'lost material ({spots}). Before committing a move, scan '
                      f'all of your opponent’s checks and captures first.')

    # missed tactics
    missed_caps = [e for e in entries if e['kind'] in ('mistake', 'blunder')
                   and 'capture you missed' in e['comment']]
    if missed_caps:
        advice.append(f'Missed tactics: you overlooked winning captures on '
                      f'{", ".join(e["label"] for e in missed_caps[:3])}. '
                      f'Each turn, look at every capture you have — even '
                      f'unlikely-looking ones.')

    missed_mates = [e for e in entries if e['missed_mate']]
    if missed_mates:
        advice.append(f'You missed a forced checkmate on '
                      f'{", ".join(e["label"] for e in missed_mates)}. When the '
                      f'enemy king is exposed, calculate checks all the way through.')

    # castling habits
    castle_ply = next((ply for ply, (m, _) in enumerate(moves)
                       if m.piece == human_color + 'K'
                       and m.flag in ('castleK', 'castleQ')), None)
    if castle_ply is None and len(moves) >= 20:
        advice.append('King safety: you never castled. Aim to castle within '
                      'the first 10 moves so your king isn’t stuck in the centre.')
    elif castle_ply is not None and castle_ply > 24:
        advice.append('King safety: you castled quite late. Try to castle '
                      'within the first 10 moves.')

    # early queen sorties
    early_queen = next((e for e in entries if e['ply'] < 8 and not e['in_book']
                        and e['san'].startswith('Q')), None)
    if early_queen and counts['blunder'] + counts['mistake'] > 0:
        advice.append(f'You brought your queen out early ({early_queen["label"]}). '
                      f'Develop knights and bishops first — an early queen '
                      f'becomes a target.')

    if counts['blunder'] == 0 and counts['mistake'] <= 1:
        advice.append('Solid game — very few serious errors. Consider raising '
                      'the difficulty for a tougher fight.')

    return {'accuracy': accuracy, 'avg_loss': avg_loss, 'counts': counts,
            'human_moves': human_plies, 'advice': advice}
