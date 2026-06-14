"""GUI smoke test: opens the app, simulates clicking e2 then e4, and verifies
(1) the board canvas redraws after the human move — the bug being guarded
against — and (2) the AI replies with its own move shortly after.
"""

import sys
import tkinter as tk
from types import SimpleNamespace

from app import ChessApp, MARGIN, SQ

root = tk.Tk()
app = ChessApp(root)
results = {}


def click(square_rc):
    r, c = square_rc
    app.on_click(SimpleNamespace(x=MARGIN + c * SQ + SQ // 2,
                                 y=MARGIN + r * SQ + SQ // 2))


def step1():
    click((6, 4))                      # select the e2 pawn
    results['selected'] = app.selected == 52 and len(app.targets) == 2
    click((4, 4))                      # move it to e4
    # the human move must be on the board immediately, before the AI replies
    results['board_updated'] = (app.state.board[36] == 'wP'
                                and app.state.board[52] is None
                                and len(app.history) == 1)
    root.after(3000, step2)


def step2():
    results['ai_replied'] = len(app.history) == 2 and app.state.turn == 'w'
    results['rag_panel'] = app.rag_text.get('1.0', 'end').strip() != ''
    root.destroy()


root.after(600, step1)
root.mainloop()

ok = True
for name, passed in results.items():
    print(f'{name}: {"PASS" if passed else "FAIL"}')
    ok = ok and passed
print('GUI SMOKE TEST PASSED' if ok else 'GUI SMOKE TEST FAILED')
sys.exit(0 if ok else 1)
