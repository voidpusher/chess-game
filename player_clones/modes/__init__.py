"""Mode system for player clones.

Multiple versions of the same clone — identical personality (style fingerprint,
opening repertoire, real-game mimicry), different strength / decision quality:

    CASUAL    "Stream Samay having fun"   — impulsive, sacrificial, ~800-1200
    REAL      "Authentic Samay clone"     — the existing engine, untouched
    PEAK      "Locked-in Samay"           — same style, near-best moves only
    ADAPTIVE  "Samay at your level"       — accuracy scales to your rating

The layer is pure composition over the existing clone engine: a mode is a
`ModeConfig` (parameter set) applied through `ModedCloneProvider`. No clone
logic, ingestion, or style analysis is duplicated or modified.
"""

from player_clones.modes.mode_config import (
    ModeConfig, CASUAL, REAL, PEAK, adaptive_config, MODE_PRESETS,
)
from player_clones.modes.moded_candidates import ModedCandidateProvider
from player_clones.modes.moded_provider import ModedCloneProvider
from player_clones.modes.samay_mode_manager import SamayModeManager, CloneModeManager

__all__ = [
    "ModeConfig", "CASUAL", "REAL", "PEAK", "adaptive_config", "MODE_PRESETS",
    "ModedCandidateProvider", "ModedCloneProvider",
    "SamayModeManager", "CloneModeManager",
]
