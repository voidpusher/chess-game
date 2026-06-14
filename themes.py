"""Theme system: board themes, app dark/light palettes, persistence, picker UI.

Single source of truth for every colour the app uses. `app.py` mirrors the
active palette into its module-level colour names (so all existing drawing code
keeps working), and the dashboard package is kept in sync via
`player_clones.dashboard.theme.apply_app_palette`.

User choices persist in `ui_settings.json` next to this file.
"""

from __future__ import annotations

import json
import os
import tkinter as tk

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "ui_settings.json")

DEFAULT_BOARD = "Walnut"
DEFAULT_MODE = "dark"

# --------------------------------------------------------------------------- #
# Board themes (5)
# --------------------------------------------------------------------------- #

BOARD_THEMES = {
    "Classic Brown": {            # lichess classic
        "light": "#f0d9b5", "dark": "#b58863",
        "last_light": "#cdd26a", "last_dark": "#aaa23a",
        "sel": "#f7ec5e", "check": "#e25b4a", "dot": "#6a9b41",
    },
    "Forest Green": {             # chess.com classic
        "light": "#eeeed2", "dark": "#769656",
        "last_light": "#f6f669", "last_dark": "#baca44",
        "sel": "#f7f769", "check": "#e2574a", "dot": "#5c7c8a",
    },
    "Ocean Blue": {
        "light": "#dee3e6", "dark": "#8ca2ad",
        "last_light": "#c8dbe8", "last_dark": "#9fbccb",
        "sel": "#aed1e6", "check": "#e25b4a", "dot": "#4a7d96",
    },
    "Royal Purple": {
        "light": "#e9e2f0", "dark": "#9f7fc4",
        "last_light": "#d9c8ec", "last_dark": "#b89ad6",
        "sel": "#cdb1e8", "check": "#e2574a", "dot": "#6c4a96",
    },
    "Walnut": {
        "light": "#e6c89c", "dark": "#a8744f",
        "last_light": "#e8d27e", "last_dark": "#c9a25a",
        "sel": "#eed676", "check": "#d94f3d", "dot": "#5e7a3a",
    },
}

# --------------------------------------------------------------------------- #
# App palettes (dark / light)
# --------------------------------------------------------------------------- #

APP_PALETTES = {
    "dark": {
        "bg": "#070b14", "panel": "#101622", "textbg": "#151b2b",
        "fg": "#f7f7fb", "muted": "#a0a7bb",
        "warn": "#f4c96c", "good": "#8ee49a", "bad": "#ff7777",
        "promo_white": "#fafafa", "promo_black": "#111111",
        "graph_axis": "#444a6b", "graph_line": "#8fd1ff",
        "buttons": {
            "primary": ("#5c57d8", "#716cff", "#ffffff"),
            "neutral": ("#1a2132", "#252d42", "#f7f7fb"),
            "success": ("#1d2638", "#2c354d", "#f7f7fb"),
            "info":    ("#1a2132", "#252d42", "#f7f7fb"),
            "accent":  ("#1a2132", "#252d42", "#f7f7fb"),
        },
        "analysis": {
            "book": "#6fb7ff", "best": "#7ce38b", "excellent": "#a5e8b0",
            "inaccuracy": "#f6d244", "mistake": "#f6a244", "blunder": "#f66a6a",
            "tip": "#a5e8b0",
        },
    },
    "light": {
        "bg": "#eef0f6", "panel": "#ffffff", "textbg": "#e7eaf3",
        "fg": "#23253a", "muted": "#666d85",
        "warn": "#9a6b00", "good": "#1e7d3c", "bad": "#c43b3b",
        "promo_white": "#9aa0b8", "promo_black": "#111111",
        "graph_axis": "#c5c9da", "graph_line": "#3b82c4",
        "buttons": {
            "primary": ("#5a67d8", "#4a55c2", "white"),
            "neutral": ("#d6dae8", "#c4c9dd", "#2b2f4a"),
            "success": ("#2f855a", "#256e4a", "white"),
            "info":    ("#2f6f85", "#265d70", "white"),
            "accent":  ("#7048b6", "#5e3a9d", "white"),
        },
        "analysis": {
            "book": "#1d6fb8", "best": "#1e7d3c", "excellent": "#3f9e58",
            "inaccuracy": "#9a6b00", "mistake": "#bf5f00", "blunder": "#c43b3b",
            "tip": "#1e7d3c",
        },
    },
}


def button_colors(mode: str, kind: str):
    """(base, hover, fg) for a button kind in the given app mode."""
    pal = APP_PALETTES.get(mode, APP_PALETTES[DEFAULT_MODE])
    return pal["buttons"].get(kind, pal["buttons"]["neutral"])


def analysis_palette(mode: str) -> dict:
    return APP_PALETTES.get(mode, APP_PALETTES[DEFAULT_MODE])["analysis"]


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass                                   # cosmetic — never break the app


# --------------------------------------------------------------------------- #
# Theme picker dialog
# --------------------------------------------------------------------------- #

def open_theme_dialog(root, current_board: str, current_mode: str,
                      on_board, on_mode):
    """Theme picker: live board-theme swatches + dark/light app mode.

    `on_board(name)` and `on_mode(mode)` are applied instantly. Switching the
    app mode rebuilds the main UI (which destroys this dialog), so the dialog
    re-opens itself to stay usable.
    """
    pal = APP_PALETTES.get(current_mode, APP_PALETTES[DEFAULT_MODE])

    dlg = tk.Toplevel(root)
    dlg.title("Appearance")
    dlg.configure(bg=pal["bg"])
    dlg.transient(root)
    dlg.resizable(False, False)

    tk.Label(dlg, text="🎨  Appearance", bg=pal["bg"], fg=pal["fg"],
             font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(14, 2))

    # ---- board themes ---------------------------------------------------- #
    tk.Label(dlg, text="Board theme", bg=pal["bg"], fg=pal["muted"],
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(8, 4))
    row = tk.Frame(dlg, bg=pal["bg"])
    row.pack(padx=14, pady=(0, 6))

    swatches = {}

    def select_board(name):
        on_board(name)
        for n, frame in swatches.items():
            frame.configure(highlightbackground=(
                "#5a67d8" if n == name else pal["bg"]))

    for name, t in BOARD_THEMES.items():
        cell = tk.Frame(row, bg=pal["bg"], highlightthickness=3,
                        highlightbackground=(
                            "#5a67d8" if name == current_board else pal["bg"]))
        cell.pack(side="left", padx=5)
        cv = tk.Canvas(cell, width=56, height=56, highlightthickness=0,
                       cursor="hand2", bg=t["dark"])
        cv.pack()
        for r in range(2):
            for c in range(2):
                color = t["light"] if (r + c) % 2 == 0 else t["dark"]
                cv.create_rectangle(c * 28, r * 28, c * 28 + 28, r * 28 + 28,
                                    fill=color, outline="")
        cv.create_oval(34, 6, 50, 22, fill=t["dot"], outline="")  # marker hint
        tk.Label(cell, text=name.split()[0], bg=pal["bg"], fg=pal["muted"],
                 font=("Segoe UI", 8)).pack()
        cv.bind("<Button-1>", lambda e, n=name: select_board(n))
        swatches[name] = cell

    # ---- app mode ---------------------------------------------------------- #
    tk.Label(dlg, text="App mode", bg=pal["bg"], fg=pal["muted"],
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(10, 4))
    mrow = tk.Frame(dlg, bg=pal["bg"])
    mrow.pack(anchor="w", padx=18, pady=(0, 8))

    def pick_mode(mode):
        if mode == current_mode:
            return
        dlg.destroy()
        on_mode(mode)                          # rebuilds the main UI
        open_theme_dialog(root, current_board, mode, on_board, on_mode)

    for mode, label in (("dark", "🌙  Dark"), ("light", "☀  Light")):
        active = mode == current_mode
        base, hover, fg = button_colors(current_mode,
                                        "primary" if active else "neutral")
        b = tk.Button(mrow, text=label, command=lambda m=mode: pick_mode(m),
                      bg=base, fg=fg, font=("Segoe UI", 10, "bold"),
                      relief="flat", bd=0, padx=18, pady=6,
                      activebackground=hover, activeforeground=fg,
                      cursor="hand2")
        b.pack(side="left", padx=(0, 8))

    base, hover, fg = button_colors(current_mode, "neutral")
    tk.Button(dlg, text="Done", command=dlg.destroy, bg=base, fg=fg,
              font=("Segoe UI", 10), relief="flat", bd=0, padx=20, pady=5,
              activebackground=hover, activeforeground=fg,
              cursor="hand2").pack(anchor="e", padx=18, pady=(4, 14))

    dlg.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - dlg.winfo_width()) // 2
    y = root.winfo_y() + 80
    dlg.geometry(f"+{x}+{y}")
    return dlg
