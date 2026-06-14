"""Style analysis (PHASE 3).

`PlayerStyleAnalyzer` turns a player's stored games + moves into a five-axis
style fingerprint (aggression / tactical / risk / king safety / endgame) plus
opening preferences and the performance breakdowns the DNA page renders.
"""

from player_clones.style_analysis.style_analyzer import PlayerStyleAnalyzer
from player_clones.style_analysis import metrics

__all__ = ["PlayerStyleAnalyzer", "metrics"]
