"""Chess.com Published-Data API client (PHASE 1).

Only the read-only public endpoints are used (no auth required):

    GET /pub/player/{username}                  -> profile
    GET /pub/player/{username}/games/archives   -> list of monthly archive URLs
    GET /pub/player/{username}/games/{YYYY}/{MM} -> that month's games (with PGN)

The client is defined behind the `ChessComSource` interface so the importer
depends on an abstraction, not on `urllib` — Dependency Inversion. The offline
`SampleChessComClient` and test fakes implement the same three methods.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Protocol

API_ROOT = "https://api.chess.com/pub"
# Chess.com requires a descriptive User-Agent or it returns 403.
_USER_AGENT = "player-clone-engine/1.0 (chess style cloning; contact: local app)"


class ChessComError(RuntimeError):
    """Raised when the Chess.com API cannot be reached or returns an error."""


class ChessComSource(Protocol):
    """The minimal surface the importer needs from any game source."""

    def get_profile(self, username: str) -> dict: ...
    def get_archives(self, username: str) -> list[str]: ...
    def get_games(self, archive_url: str) -> list[dict]: ...


class ChessComClient:
    """Live HTTP client for the Chess.com public API."""

    def __init__(self, timeout: float = 15.0, retries: int = 2,
                 pause: float = 0.4):
        self.timeout = timeout
        self.retries = retries
        self.pause = pause          # polite delay between archive fetches

    # -- low level ---------------------------------------------------------- #
    def _get_json(self, url: str) -> dict:
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": _USER_AGENT,
                                  "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise ChessComError(f"Not found: {url}") from e
                last_err = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_err = e
            if attempt < self.retries:
                time.sleep(self.pause * (attempt + 1))
        raise ChessComError(f"Failed to fetch {url}: {last_err}")

    # -- public API --------------------------------------------------------- #
    def get_profile(self, username: str) -> dict:
        return self._get_json(f"{API_ROOT}/player/{username.lower()}")

    def get_archives(self, username: str) -> list[str]:
        data = self._get_json(
            f"{API_ROOT}/player/{username.lower()}/games/archives")
        return list(data.get("archives", []))

    def get_games(self, archive_url: str) -> list[dict]:
        if self.pause:
            time.sleep(self.pause)
        data = self._get_json(archive_url)
        return list(data.get("games", []))
