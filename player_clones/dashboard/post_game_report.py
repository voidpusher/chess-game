"""Post-game report shown after a game against a clone (PHASE 8).

    Played Against:
    Samay Style Clone

Shows the opening used, the clone's aggression / tactical / risk scores, and —
crucially — *which style features actually influenced this game*, derived from
the live influence tally the clone engine accumulated move by move.
"""

from __future__ import annotations

import tkinter as tk

from player_clones.dashboard import theme as T

# Human-readable names + explanations for the influence keys the engine tracks.
_FEATURE_LABELS = {
    "repertoire": ("Repertoire mimicry", "played his real, known moves in positions he has faced"),
    "sacrifice": ("Sacrifices", "gave up material for attacking initiative"),
    "check": ("Checks", "kept your king under direct fire"),
    "capture": ("Captures", "favoured forcing, material-grabbing play"),
    "king_attack": ("King-hunt", "steered pieces toward your king"),
    "fork": ("Forks", "looked for double attacks"),
    "advance": ("Advancing", "pushed pieces into your half"),
    "central": ("Central control", "fought for the centre"),
    "mate": ("Mating attack", "went straight for checkmate"),
    "castle": ("Castling", "tucked the king away early"),
    "king_walk": ("King activity", "marched the king into the action"),
    "development": ("Development", "brought pieces out quickly"),
    "promotion": ("Promotion", "pushed passed pawns to queen"),
}


def open_post_game_report(parent, provider, opening_used: str,
                          result_text: str = "") -> tk.Toplevel:
    headline = provider.profile.headline()
    influence = provider.influence_summary() if hasattr(provider, "influence_summary") else []

    win = tk.Toplevel(parent)
    win.title("Post-Game Report")
    win.configure(bg=T.BG)
    win.geometry("520x620")

    head = tk.Frame(win, bg=T.PANEL, padx=18, pady=14)
    head.pack(fill="x", padx=14, pady=(14, 8))
    tk.Label(head, text="Played Against:", bg=T.PANEL, fg=T.MUTED,
             font=("Segoe UI", 10)).pack(anchor="w")
    tk.Label(head, text=provider.display_name, bg=T.PANEL, fg=T.FG,
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    mode = getattr(provider, "mode", None)
    if mode is not None:
        tk.Label(head, text=f"Estimated strength: {mode.strength}",
                 bg=T.PANEL, fg=T.MUTED, font=("Segoe UI", 9)).pack(anchor="w")
    if result_text:
        tk.Label(head, text=result_text, bg=T.PANEL, fg=T.FG,
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 0))

    info = tk.Frame(win, bg=T.TEXTBG, padx=18, pady=12)
    info.pack(fill="x", padx=14)
    tk.Label(info, text=f"Opening used:  {opening_used or 'Unknown'}",
             bg=T.TEXTBG, fg=T.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w")

    scores = tk.Frame(win, bg=T.TEXTBG, padx=18, pady=12)
    scores.pack(fill="x", padx=14, pady=(8, 0))
    tk.Label(scores, text="Style profile in play", bg=T.TEXTBG, fg=T.MUTED,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
    for key, label in (("aggression", "Aggression"), ("tactical", "Tactical"),
                       ("risk", "Risk")):
        _bar(scores, label, int(headline.get(key, 0)),
             T.AXIS_COLORS.get(key, T.ACCENT))

    feats = tk.Frame(win, bg=T.BG, padx=4, pady=8)
    feats.pack(fill="both", expand=True, padx=14, pady=(10, 14))
    tk.Label(feats, text="Style features that influenced this game",
             bg=T.BG, fg=T.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w",
                                                                    pady=(0, 6))
    shown = [(k, v) for k, v in influence if v > 0][:7]
    if not shown:
        tk.Label(feats, text="A short game — not enough moves to fingerprint.",
                 bg=T.BG, fg=T.MUTED, font=("Segoe UI", 10, "italic")).pack(anchor="w")
    else:
        peak = shown[0][1]
        for key, weight in shown:
            label, desc = _FEATURE_LABELS.get(key, (key.title(), ""))
            line = tk.Frame(feats, bg=T.TEXTBG, padx=12, pady=8)
            line.pack(fill="x", pady=3)
            top = tk.Frame(line, bg=T.TEXTBG)
            top.pack(fill="x")
            tk.Label(top, text=f"• {label}", bg=T.TEXTBG, fg=T.FG,
                     font=("Segoe UI", 11, "bold")).pack(side="left")
            cv = tk.Canvas(top, width=120, height=10, bg=T.BG, highlightthickness=0)
            cv.pack(side="right")
            frac = max(0.08, min(1.0, weight / peak)) if peak else 0.0
            cv.create_rectangle(0, 0, 120 * frac, 10, fill=T.AXIS_COLORS["aggression"],
                                outline="")
            tk.Label(line, text=desc, bg=T.TEXTBG, fg=T.MUTED, anchor="w",
                     wraplength=440, justify="left",
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

    return win


def _bar(parent, label, value, color):
    row = tk.Frame(parent, bg=T.TEXTBG)
    row.pack(fill="x", pady=2)
    tk.Label(row, text=label, bg=T.TEXTBG, fg=T.FG, width=12, anchor="w",
             font=("Segoe UI", 10)).pack(side="left")
    cv = tk.Canvas(row, width=300, height=14, bg=T.BG, highlightthickness=0)
    cv.pack(side="left", padx=6)
    cv.create_rectangle(0, 1, 300 * max(0, min(100, value)) / 100, 13,
                        fill=color, outline="")
    tk.Label(row, text=str(value), bg=T.TEXTBG, fg=T.MUTED,
             font=("Segoe UI", 9)).pack(side="left")
