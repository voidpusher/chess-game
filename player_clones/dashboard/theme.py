"""Shared dashboard palette — kept in sync with the app's active theme.

Defaults to the dark chrome; `apply_app_palette` (called by the app whenever
the user switches dark/light mode) re-points these names. All dashboard views
read them at construction time, so windows opened after a switch match.
"""

BG = "#262837"
PANEL = "#2e3147"
TEXTBG = "#23253a"
FG = "#e8e8ee"
MUTED = "#9aa0b8"
ACCENT = "#5a67d8"


def apply_app_palette(p: dict) -> None:
    """Adopt the app-level palette (see themes.APP_PALETTES)."""
    global BG, PANEL, TEXTBG, FG, MUTED
    BG = p["bg"]
    PANEL = p["panel"]
    TEXTBG = p["textbg"]
    FG = p["fg"]
    MUTED = p["muted"]

# Per-axis bar colours for the DNA fingerprint.
AXIS_COLORS = {
    "aggression": "#f6694a",
    "tactical": "#8fd1ff",
    "risk": "#f6c244",
    "kingSafety": "#7ce38b",
    "endgame": "#b78cff",
}

WIN = "#7ce38b"
LOSS = "#f66a6a"
DRAW = "#9aa0b8"
