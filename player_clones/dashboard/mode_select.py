"""Mode selection screen — "Play Against Samay → Choose Mode".

`ask_mode(parent, current_key, current_rating)` opens a modal dialog showing the
four modes as cards (name, description, estimated strength) plus a rating
spinner that activates for Adaptive. Returns ``(mode_key, user_rating)`` or
``None`` if cancelled.
"""

from __future__ import annotations

import tkinter as tk

from player_clones.dashboard import theme as T
from player_clones.modes.mode_config import CASUAL, REAL, PEAK, adaptive_config

_CARD_ORDER = ("casual", "real", "peak", "adaptive")
_ACCENTS = {"casual": "#f6c244", "real": "#5a67d8",
            "peak": "#f6694a", "adaptive": "#7ce38b"}


def _mode_info(key: str, rating: int):
    if key == "adaptive":
        cfg = adaptive_config(rating)
    else:
        cfg = {"casual": CASUAL, "real": REAL, "peak": PEAK}[key]
    return cfg.title, cfg.description, cfg.strength


def ask_mode(parent, current_key: str = "real",
             current_rating: int = 1200):
    result = {}

    dlg = tk.Toplevel(parent)
    dlg.title("Play Against Samay — Choose Mode")
    dlg.configure(bg=T.BG)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    tk.Label(dlg, text="♚  Play Against Samay", bg=T.BG, fg=T.FG,
             font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=18, pady=(14, 0))
    tk.Label(dlg, text="Choose Mode — same personality, different strength",
             bg=T.BG, fg=T.MUTED, font=("Segoe UI", 10)).pack(anchor="w",
                                                              padx=18, pady=(0, 8))

    var = tk.StringVar(value=current_key if current_key in _CARD_ORDER else "real")
    rating_var = tk.IntVar(value=current_rating)
    strength_labels = {}

    def refresh(*_):
        for k, lbl in strength_labels.items():
            _, _, strength = _mode_info(k, rating_var.get())
            lbl.configure(text=f"Estimated strength:  {strength}")
        spin.configure(state="normal" if var.get() == "adaptive" else "disabled")

    cards = tk.Frame(dlg, bg=T.BG)
    cards.pack(fill="x", padx=14)
    for key in _CARD_ORDER:
        title, desc, strength = _mode_info(key, rating_var.get())
        card = tk.Frame(cards, bg=T.PANEL, padx=12, pady=8,
                        highlightbackground=_ACCENTS[key], highlightthickness=2)
        card.pack(fill="x", pady=4)
        top = tk.Frame(card, bg=T.PANEL)
        top.pack(fill="x")
        tk.Radiobutton(top, text=title, variable=var, value=key,
                       command=refresh, bg=T.PANEL, fg=T.FG,
                       selectcolor=T.TEXTBG, activebackground=T.PANEL,
                       activeforeground=T.FG,
                       font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(card, text=desc, bg=T.PANEL, fg=T.MUTED, wraplength=470,
                 justify="left", font=("Segoe UI", 9)).pack(anchor="w",
                                                            padx=(24, 0))
        sl = tk.Label(card, text=f"Estimated strength:  {strength}",
                      bg=T.PANEL, fg=_ACCENTS[key],
                      font=("Segoe UI", 9, "bold"))
        sl.pack(anchor="w", padx=(24, 0), pady=(2, 0))
        strength_labels[key] = sl

        # clicking anywhere on the card selects the mode
        for w in (card, top):
            w.bind("<Button-1>", lambda e, k=key: (var.set(k), refresh()))

    rrow = tk.Frame(dlg, bg=T.BG)
    rrow.pack(fill="x", padx=18, pady=(8, 0))
    tk.Label(rrow, text="Your rating (for Adaptive):", bg=T.BG, fg=T.MUTED,
             font=("Segoe UI", 10)).pack(side="left")
    spin = tk.Spinbox(rrow, from_=400, to=2400, increment=50,
                      textvariable=rating_var, width=6, bg=T.TEXTBG, fg=T.FG,
                      buttonbackground=T.PANEL, relief="flat",
                      font=("Segoe UI", 10), command=refresh)
    spin.pack(side="left", padx=8)
    rating_var.trace_add("write", lambda *_: refresh())

    btns = tk.Frame(dlg, bg=T.BG)
    btns.pack(fill="x", padx=18, pady=14)

    def ok():
        try:
            rating = max(400, min(2400, int(rating_var.get())))
        except (tk.TclError, ValueError):
            rating = 1200
        result["value"] = (var.get(), rating)
        dlg.destroy()

    tk.Button(btns, text="Play", command=ok, bg="#5a67d8", fg="white",
              font=("Segoe UI", 11, "bold"), relief="flat", padx=22, pady=6,
              activebackground="#6b77e8", cursor="hand2").pack(side="left")
    tk.Button(btns, text="Cancel", command=dlg.destroy, bg="#3a3f63", fg="white",
              font=("Segoe UI", 10), relief="flat", padx=14, pady=6,
              activebackground="#4a4f78", cursor="hand2").pack(side="left", padx=8)

    refresh()
    dlg.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - dlg.winfo_width()) // 2
    y = parent.winfo_y() + max(20, (parent.winfo_height() - dlg.winfo_height()) // 2)
    dlg.geometry(f"+{x}+{y}")
    parent.wait_window(dlg)
    return result.get("value")
