"""The player DNA page (PHASE 7).

`open_dna_page(parent, dna)` opens a scrollable tkinter window rendering a
clone's fingerprint and performance charts from the dict returned by
`provider.dna()`:

    * total games analyzed, overall win rate
    * the five style scores as labelled bars
    * opening distribution (most-played openings)
    * win rate by opening
    * White vs Black performance
    * time-control performance

Pure Tk/Canvas — no third-party charting, consistent with the project.
"""

from __future__ import annotations

import tkinter as tk

from player_clones.dashboard import theme as T

_AXIS_LABELS = [
    ("aggression", "Aggression"),
    ("tactical", "Tactical"),
    ("risk", "Risk"),
    ("kingSafety", "King Safety"),
    ("endgame", "Endgame"),
]


def open_dna_page(parent, dna: dict) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(f"{dna.get('display_name', 'Player')} — DNA")
    win.configure(bg=T.BG)
    win.geometry("760x820")

    # scrollable body
    canvas = tk.Canvas(win, bg=T.BG, highlightthickness=0)
    scroll = tk.Scrollbar(win, command=canvas.yview)
    body = tk.Frame(canvas, bg=T.BG)
    body.bind("<Configure>",
              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    perf = dna.get("performance", {})
    overall = perf.get("overall", {})

    _header(body, dna, overall)
    _section(body, "Style Fingerprint")
    _fingerprint_bars(body, dna.get("headline", {}))
    _section(body, "Opening Distribution")
    _opening_distribution(body, perf.get("by_opening", []))
    _section(body, "Win Rate by Opening")
    _winrate_by_opening(body, perf.get("by_opening", []))
    _section(body, "White vs Black")
    _color_performance(body, perf.get("by_color", {}))
    _section(body, "Time Control Performance")
    _time_performance(body, perf.get("by_time_control", {}))

    return win


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

def _header(parent, dna, overall):
    head = tk.Frame(parent, bg=T.PANEL, padx=18, pady=14)
    head.pack(fill="x", padx=14, pady=(14, 6))
    tk.Label(head, text=f"\U0001F9EC  {dna.get('display_name','Player')} DNA",
             bg=T.PANEL, fg=T.FG, font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(head, text=f"@{dna.get('username','')}  ·  source: Chess.com",
             bg=T.PANEL, fg=T.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
    games = dna.get("total_games", 0)
    wr = overall.get("win_rate", 0.0)
    rec = f"{overall.get('wins',0)}W / {overall.get('losses',0)}L / {overall.get('draws',0)}D"
    tk.Label(head, text=f"{games} games analyzed   ·   {wr:.1f}% win rate   ·   {rec}",
             bg=T.PANEL, fg=T.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w",
                                                                      pady=(6, 0))


def _section(parent, title):
    tk.Label(parent, text=title, bg=T.BG, fg=T.FG, anchor="w",
             font=("Segoe UI", 12, "bold")).pack(fill="x", padx=16, pady=(14, 2))


def _fingerprint_bars(parent, headline):
    frame = tk.Frame(parent, bg=T.TEXTBG, padx=16, pady=12)
    frame.pack(fill="x", padx=14)
    for key, label in _AXIS_LABELS:
        val = int(headline.get(key, 0))
        _labeled_bar(frame, label, val, 100, T.AXIS_COLORS.get(key, T.ACCENT),
                     suffix=str(val))


def _opening_distribution(parent, by_opening):
    frame = tk.Frame(parent, bg=T.TEXTBG, padx=16, pady=12)
    frame.pack(fill="x", padx=14)
    rows = by_opening[:8]
    if not rows:
        _empty(frame)
        return
    top = max(r["games"] for r in rows)
    for r in rows:
        _labeled_bar(frame, r["opening"][:28], r["games"], top, T.ACCENT,
                     suffix=f"{r['games']}")


def _winrate_by_opening(parent, by_opening):
    frame = tk.Frame(parent, bg=T.TEXTBG, padx=16, pady=12)
    frame.pack(fill="x", padx=14)
    rows = [r for r in by_opening if r["games"] >= 1][:8]
    if not rows:
        _empty(frame)
        return
    for r in rows:
        color = T.WIN if r["win_rate"] >= 55 else T.LOSS if r["win_rate"] < 45 else T.DRAW
        _labeled_bar(frame, r["opening"][:28], r["win_rate"], 100, color,
                     suffix=f"{r['win_rate']:.0f}%  ({r['games']}g)")


def _color_performance(parent, by_color):
    frame = tk.Frame(parent, bg=T.TEXTBG, padx=16, pady=12)
    frame.pack(fill="x", padx=14)
    if not by_color:
        _empty(frame)
        return
    for color in ("white", "black"):
        d = by_color.get(color, {})
        label = f"As {color.capitalize()}"
        wr = d.get("win_rate", 0.0)
        suffix = f"{wr:.0f}%  ({d.get('games',0)}g: " \
                 f"{d.get('wins',0)}/{d.get('losses',0)}/{d.get('draws',0)})"
        _labeled_bar(frame, label, wr, 100,
                     "#f0f0f0" if color == "white" else "#555a7a", suffix=suffix)


def _time_performance(parent, by_time):
    frame = tk.Frame(parent, bg=T.TEXTBG, padx=16, pady=12)
    frame.pack(fill="x", padx=14, pady=(0, 16))
    if not by_time:
        _empty(frame)
        return
    order = ["bullet", "blitz", "rapid", "classical", "daily", "unknown"]
    items = sorted(by_time.items(), key=lambda kv: order.index(kv[0])
                   if kv[0] in order else 99)
    for tc, d in items:
        wr = d.get("win_rate", 0.0)
        suffix = f"{wr:.0f}%  ({d.get('games',0)}g)"
        _labeled_bar(frame, tc.capitalize(), wr, 100, T.AXIS_COLORS["tactical"],
                     suffix=suffix)


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #

def _labeled_bar(parent, label, value, maximum, color, suffix=""):
    row = tk.Frame(parent, bg=parent["bg"])
    row.pack(fill="x", pady=3)
    tk.Label(row, text=label, bg=parent["bg"], fg=T.FG, width=18, anchor="w",
             font=("Segoe UI", 10)).pack(side="left")
    bar_w = 360
    cv = tk.Canvas(row, width=bar_w, height=16, bg=T.BG, highlightthickness=0)
    cv.pack(side="left", padx=8)
    frac = 0.0 if maximum <= 0 else max(0.0, min(1.0, value / maximum))
    cv.create_rectangle(0, 2, bar_w, 14, fill="#1b1d2e", outline="")
    if frac > 0:
        cv.create_rectangle(0, 2, max(2, bar_w * frac), 14, fill=color, outline="")
    tk.Label(row, text=suffix, bg=parent["bg"], fg=T.MUTED, anchor="w",
             font=("Segoe UI", 9)).pack(side="left")


def _empty(parent):
    tk.Label(parent, text="No data yet.", bg=parent["bg"], fg=T.MUTED,
             font=("Segoe UI", 10, "italic")).pack(anchor="w")
