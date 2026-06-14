"""Chess.com ingestion (PHASE 1).

`PlayerImporterService` pulls a public account's monthly archives, stores games,
and parses them into per-move records. The actual HTTP is behind a
`ChessComSource` interface so it can be swapped for the bundled offline sample
(or a mock in tests) without touching the importer.
"""

from player_clones.importer.player_importer import (
    PlayerImporterService, ImportSummary,
)
from player_clones.importer.chesscom_client import (
    ChessComSource, ChessComClient, ChessComError,
)
from player_clones.importer.sample_data import SampleChessComClient

__all__ = [
    "PlayerImporterService", "ImportSummary",
    "ChessComSource", "ChessComClient", "ChessComError", "SampleChessComClient",
]
