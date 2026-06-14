"""GUI smoke test for the Player Clone integration.

Opens the app, switches the opponent to the Samay clone, plays 1.e4 as White,
and verifies the clone (a) loads, (b) replies with a legal move, and (c) the
Samay DNA window opens. Mirrors test_gui.py's event-pump style.
"""

import sys
import tkinter as tk
from types import SimpleNamespace

from app import ChessApp, MARGIN, SQ, CLONE_MENU_LABEL

root = tk.Tk()
app = ChessApp(root)
results = {}


def click(square_rc):
    r, c = square_rc
    app.on_click(SimpleNamespace(x=MARGIN + c * SQ + SQ // 2,
                                 y=MARGIN + r * SQ + SQ // 2))


def start():
    # The arena layout surfaces the matchup in the header (match_title/subtitle);
    # the difficulty combobox is a vestigial state holder in this design. Vs the
    # computer, the header names the computer and the subtitle shows the level.
    root.update_idletasks()
    results['difficulty_shown_vs_computer'] = (
        app.match_title.cget('text') == 'Playing vs Computer'
        and app.difficulty.get().title() in app.match_subtitle.cget('text'))
    app.opponent.set(CLONE_MENU_LABEL)        # choose "Play Against Samay"
    app.new_game()                            # human = White, clone = Black
    root.update_idletasks()
    # vs Samay the header switches to the clone; his mode replaces the difficulty
    results['samay_shown_vs_samay'] = 'Samay' in app.match_title.cget('text')
    results['banter_greeting'] = '\U0001F3A4' in app.rag_text.get('1.0', 'end')
    root.after(400, play_human)


def play_human():
    click((6, 4))                             # select e2
    click((4, 4))                             # play e4
    results['human_moved'] = (app.state.board[36] == 'wP'
                              and len(app.history) == 1)
    # clone loads (building the manager over the real 21k-game DB can take
    # several seconds on a loaded machine), then replies — poll up to ~20s
    poll_clone(40)


def poll_clone(tries):
    if len(app.history) >= 2 or tries <= 0:
        check_clone()
    else:
        root.after(500, lambda: poll_clone(tries - 1))


def check_clone():
    results['clone_loaded'] = app.clone_provider is not None
    results['clone_replied'] = len(app.history) == 2 and app.state.turn == 'w'
    # the clone's reply must be a legal SAN that actually got played
    results['reply_is_real'] = (len(app.history) == 2
                                and bool(app.history[1]['san']))
    open_dna()


def open_dna():
    before = len(root.winfo_children())
    app.show_samay_dna()
    root.after(500, lambda: finish(before))


def finish(before):
    results['dna_opened'] = len(root.winfo_children()) > before
    root.destroy()


root.after(500, start)
root.mainloop()

ok = True
for name, passed in results.items():
    print(f'{name}: {"PASS" if passed else "FAIL"}')
    ok = ok and passed
print('CLONE GUI SMOKE TEST PASSED' if ok else 'CLONE GUI SMOKE TEST FAILED')
sys.exit(0 if ok else 1)
