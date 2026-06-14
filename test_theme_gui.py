"""GUI smoke test for the theme system.

Cycles every board theme, toggles light/dark app mode (full UI rebuild), and
verifies persistence — without destroying game state.
"""

import json
import os
import sys
import tkinter as tk

import themes
import app as appmod
from app import ChessApp

root = tk.Tk()
app = ChessApp(root)
results = {}


def run():
    # --- all five board themes apply and redraw ---------------------------- #
    seen_light = set()
    for name in themes.BOARD_THEMES:
        app.set_board_theme(name)
        seen_light.add(appmod.LIGHT)
    results['five_board_themes'] = len(seen_light) == len(themes.BOARD_THEMES) == 5

    # --- light mode rebuilds the UI with the light palette ----------------- #
    app.difficulty.set('hard')                      # must survive the rebuild
    before_history = len(app.history)
    app.set_app_mode('light')
    results['light_mode_applied'] = appmod.BG == themes.APP_PALETTES['light']['bg']
    results['rebuild_kept_state'] = (app.difficulty.get() == 'hard'
                                     and len(app.history) == before_history)
    # dashboards follow the app palette
    from player_clones.dashboard import theme as T
    results['dashboard_synced'] = T.BG == themes.APP_PALETTES['light']['bg']

    # --- settings persisted ------------------------------------------------ #
    with open(themes.SETTINGS_PATH, encoding='utf-8') as f:
        saved = json.load(f)
    results['persisted'] = saved.get('app_mode') == 'light'

    # --- back to dark ------------------------------------------------------- #
    app.set_app_mode('dark')
    results['dark_mode_back'] = appmod.BG == themes.APP_PALETTES['dark']['bg']
    app.set_board_theme(themes.DEFAULT_BOARD)       # leave defaults behind

    # --- theme dialog opens -------------------------------------------------- #
    dlg = app.open_theme_dialog()
    results['dialog_opens'] = any(isinstance(w, tk.Toplevel)
                                  for w in root.winfo_children())
    root.destroy()


root.after(400, run)
root.mainloop()

ok = True
for name, passed in results.items():
    print(f'{name}: {"PASS" if passed else "FAIL"}')
    ok = ok and passed
print('THEME GUI SMOKE TEST PASSED' if ok else 'THEME GUI SMOKE TEST FAILED')
sys.exit(0 if ok else 1)
