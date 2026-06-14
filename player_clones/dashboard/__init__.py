"""Dashboard UI (PHASE 7 + 8).

In-app tkinter views: the player "DNA" page (style fingerprint + performance
charts) and the post-game report shown after a game against a clone.
"""

from player_clones.dashboard.dna_view import open_dna_page
from player_clones.dashboard.post_game_report import open_post_game_report

__all__ = ["open_dna_page", "open_post_game_report"]
