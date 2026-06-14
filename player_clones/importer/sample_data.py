"""Bundled offline game sample + a `ChessComSource` that serves it (PHASE 1).

Why this exists: the importer talks to the live Chess.com API, but the clone
system must also work with **no network** (offline demos, CI, deterministic
tests, and a usable "Play Against Samay" out of the box before a real sync).

The sample is built from classic attacking master games — sacrificial, tactical,
king-hunt chess — which is exactly the aggressive/high-risk fingerprint the
Samay clone should exhibit. Every score below replays legally through `engine`
(they are validated by `test_player_clones.py`). `samayraina` is cast as the
winning side in each so the resulting profile is a decisive attacker.

For a *real* fingerprint, run a live import:  `python -m player_clones.cli import samayraina`
"""

from __future__ import annotations

# (white, black, result, eco, opening, eco_url_slug, date, time_control, time_class, moves)
_SAMPLE = [
    ("samayraina", "ChessFan_99", "1-0", "C41", "Philidor Defense",
     "Philidor-Defense", "2024.01.04", "180", "blitz",
     "e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 Nc3 c6 Bg5 b5 "
     "Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#"),
    ("samayraina", "GambitLover", "1-0", "C33", "King's Gambit Accepted",
     "Kings-Gambit-Accepted", "2024.01.07", "300", "blitz",
     "e4 e5 f4 exf4 Bc4 Qh4+ Kf1 b5 Bxb5 Nf6 Nf3 Qh6 d3 Nh5 Nh4 Qg5 Nf5 c6 g4 "
     "Nf6 Rg1 cxb5 h4 Qg6 h5 Qg5 Qf3 Ng8 Bxf4 Qf6 Nc3 Bc5 Nd5 Qxb2 Bd6 Bxg1 e5 "
     "Qxa1+ Ke2 Na6 Nxg7+ Kd8 Qf6+ Nxf6 Be7#"),
    ("samayraina", "RookiePlayer", "1-0", "C50", "Italian Game",
     "Italian-Game", "2024.01.09", "180", "blitz",
     "e4 e5 Bc4 d6 Nf3 Bg4 Nc3 g6 Nxe5 Bxd1 Bxf7+ Ke7 Nd5#"),
    ("samayraina", "BlitzBuddy", "1-0", "C20", "King's Pawn Game",
     "Kings-Pawn-Game", "2024.01.11", "60", "bullet",
     "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#"),
    ("AttackingFoe", "samayraina", "0-1", "A40", "Englund Gambit",
     "Englund-Gambit", "2024.01.15", "180", "blitz",
     "d4 e5 dxe5 Nc6 Nf3 Qe7 Bf4 Qb4+ Bd2 Qxb2 Bc3 Bb4 Qd2 Bxc3 Qxc3 Qc1#"),
    ("HopefulMaster", "samayraina", "0-1", "A00", "Barnes Opening",
     "Barnes-Opening", "2024.01.18", "120", "bullet",
     "f3 e5 g4 Qh4#"),

    # ----------------------------------------------------------------- #
    # Expanded sample (24 more) — every move sequence below replays
    # legally through `engine` (validated; mate-ending games actually
    # terminate, ongoing games are framed as resignations/draws). The mix
    # mirrors Samay's repertoire: e4/King's Gambit/Italian/London as White;
    # Sicilian/KID/Englund as Black; lots of sacrifices, ~65% wins.
    # ----------------------------------------------------------------- #

    # --- Samay as White, attacking wins (mostly checkmates) ---
    ("samayraina", "blitz_arjun_07", "1-0", "C57", "Italian Game: Two Knights",
     "Italian-Game-Two-Knights-Defense", "2024.02.02", "180", "blitz",
     "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Na5 Bb5+ c6 dxc6 bxc6 Qf3 cxb5 Qxa8 Qc7"),  # resign, big material
    ("samayraina", "TacticsAreLife", "1-0", "C30", "King's Gambit Declined",
     "Kings-Gambit-Declined", "2024.02.05", "300", "blitz",
     "e4 e5 f4 exf4 Nf3 g5 Bc4 g4 O-O gxf3 Qxf3 Qf6 e5 Qxe5 Bxf7+ Kxf7 d4 Qxd4+ "
     "Be3 Qf6 Bxf4 Ke8 Nc3"),  # heavy attack, resign
    ("samayraina", "NihalFanBoy", "1-0", "C27", "Vienna Gambit",
     "Vienna-Game", "2024.02.08", "180", "blitz",
     "e4 e5 Nc3 Nf6 f4 d5 fxe5 Nxe4 Nf3 Be7 d4 O-O Bd3 f5 exf6 Nxf6"),  # resign, strong centre
    ("samayraina", "CarlsenWannabe", "1-0", "C44", "Scotch Game",
     "Scotch-Game", "2024.02.11", "600", "rapid",
     "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nxc6 bxc6 e5 Qe7 Qe2 Nd5 c4 Ba6 b3 g6"),  # resign
    ("samayraina", "patzer_pranav", "1-0", "C50", "Italian Game",
     "Italian-Game", "2024.02.14", "180", "blitz",
     "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+ Bd2 Bxd2+ Nbxd2 d5 exd5 Nxd5 O-O O-O"),  # resign
    ("samayraina", "rookie_rohan", "1-0", "B01", "Scandinavian Defense",
     "Scandinavian-Defense", "2024.02.17", "60", "bullet",
     "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 c6 Bc4 Bf5 Bd2 e6 Nd5 Qd8"),  # resign
    ("samayraina", "DragonSlayer22", "1-0", "C29", "Vienna: Falkbeer",
     "Vienna-Game", "2024.02.20", "300", "blitz",
     "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#"),  # scholar's mate pattern
    ("samayraina", "blunder_king_99", "1-0", "C41", "Philidor / Legal",
     "Philidor-Defense", "2024.02.23", "60", "bullet",
     "e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5 Bxd1 Bxf7+ Ke7 Nd5#"),  # Legal's mate
    ("samayraina", "vidit_respecter", "1-0", "C33", "King's Gambit Accepted",
     "Kings-Gambit-Accepted", "2024.03.01", "300", "blitz",
     "e4 e5 f4 exf4 Bc4 Qh4+ Kf1 b5 Bxb5 Nf6 Nf3 Qh6 d3 Nh5 Nh4 Qg5 Nf5 c6 g4 "
     "Nf6 Rg1 cxb5 h4 Qg6 h5 Qg5 Qf3 Ng8 Bxf4 Qf6 Nc3 Bc5 Nd5 Qxb2 Bd6 Bxg1 e5 "
     "Qxa1+ Ke2 Na6 Nxg7+ Kd8 Qf6+ Nxf6 Be7#"),  # immortal-game finish
    ("samayraina", "chesscom_cheater", "1-0", "C52", "Evans Gambit",
     "Evans-Gambit", "2024.03.04", "180", "blitz",
     "e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O d3 Qb3 Qf6 e5 Qg6 Re1 "
     "Nge7 Ba3 b5 Qxb5 Rb8 Qa4 Bb6 Nbd2 Bb7 Ne4 Qf5 Bxd3 Qh5 Nf6+ gxf6 exf6 Rg8 "
     "Rad1 Qxf3 Rxe7+ Nxe7 Qxd7+ Kxd7 Bf5+ Ke8 Bd7+ Kf8 Bxe7#"),  # evergreen finish

    # --- Samay as White, London / quiet (a draw or two) ---
    ("samayraina", "solid_sameer", "1/2-1/2", "D02", "London System",
     "London-System", "2024.03.07", "600", "rapid",
     "d4 d5 Nf3 Nf6 Bf4 e6 e3 Bd6 Bg3 O-O Bd3 c5 c3 Nc6 Nbd2 b6"),  # draw agreed
    ("samayraina", "london_hater", "1-0", "D02", "London System",
     "London-System", "2024.03.10", "180", "blitz",
     "d4 d5 Bf4 Nf6 e3 e6 Nf3 Bd6 Bg3 O-O Bd3 b6 Nbd2 Bb7 Ne5 Nbd7"),  # resign

    # --- Samay as White, losses (over-sacrificed / blundered) ---
    ("samayraina", "QuietPositional", "0-1", "B22", "Sicilian: Alapin",
     "Sicilian-Defense-Alapin-Variation", "2024.03.13", "60", "bullet",
     "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be2 Bg7 O-O O-O"),  # resign — Samay overpressed
    ("samayraina", "EndgameGrinder", "0-1", "C68", "Ruy Lopez: Exchange",
     "Ruy-Lopez-Exchange-Variation", "2024.03.16", "600", "rapid",
     "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7"),  # resign

    # --- Samay as Black vs e4: Sicilian ---
    ("SystemPlayer_X", "samayraina", "0-1", "B90", "Sicilian: Najdorf",
     "Sicilian-Defense-Najdorf-Variation", "2024.03.19", "180", "blitz",
     "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Bg5 e6 f4 Be7 Qf3 h6 Bh4 g5 fxg5 Nfd7"),  # resign, Samay better
    ("anti_sicilian_andy", "samayraina", "0-1", "B27", "Sicilian Defense",
     "Sicilian-Defense", "2024.03.22", "300", "blitz",
     "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be2 Bg7 O-O O-O"),  # resign
    ("d4_only_dude", "samayraina", "1-0", "B70", "Sicilian: Dragon",
     "Sicilian-Defense-Dragon-Variation", "2024.03.25", "60", "bullet",
     "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6"),  # Samay lost on time, resign-style

    # --- Samay as Black vs d4: Englund + KID ---
    ("StoneWallSam", "samayraina", "0-1", "A40", "Englund Gambit",
     "Englund-Gambit", "2024.03.28", "180", "blitz",
     "d4 e5 dxe5 Nc6 Nf3 Qe7 Bf4 Qb4+ Bd2 Qxb2 Bc3 Bb4 Qd2 Bxc3 Qxc3 Qc1#"),  # Englund trap mate
    ("queens_gambit_qg", "samayraina", "0-1", "E60", "King's Indian Defense",
     "Kings-Indian-Defense", "2024.04.01", "600", "rapid",
     "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7"),  # resign, Samay better
    ("budapest_basher", "samayraina", "0-1", "A52", "Budapest Gambit",
     "Budapest-Gambit", "2024.04.04", "180", "blitz",
     "d4 Nf6 c4 e5 dxe5 Ng4 Bf4 Nc6 Nf3 Bb4+ Nbd2 Qe7 a3 Ngxe5 axb4 Nd3#"),  # Budapest smothered mate

    # --- Samay as Black vs e4: tactical wins ---
    ("caro_kann_carl", "samayraina", "0-1", "B19", "Caro-Kann: Classical",
     "Caro-Kann-Defense-Classical-Variation", "2024.04.07", "300", "blitz",
     "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 "
     "Qxd3 e6 Bd2 Ngf6 O-O-O Be7"),  # resign, Samay equal/better
    ("reti_rishi", "samayraina", "0-1", "B12", "Caro-Kann Defense",
     "Caro-Kann-Defense", "2024.04.10", "60", "bullet",
     "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6 Qd3 e5 dxe5 Qa5+ Bd2 Qxe5 O-O-O Nxe4 Qd8+ "
     "Kxd8 Bg5+ Ke8 Rd8#"),  # Reti-Tartakower mate (full)

    # --- one more decisive Samay White win, blitz ---
    ("greco_grinder", "samayraina", "1-0", "C53", "Italian Game: Greco",
     "Italian-Game", "2024.04.13", "180", "blitz",
     "e4 e5 Bc4 Bc5 Qe2 d6 f4 Nf6 Nf3 Ng4 f5 Nf2 Qxf2 Bxf2+ Kxf2"),  # resign, Samay up material
    ("samayraina", "damiano_dev", "1-0", "C40", "Damiano Defense",
     "Damiano-Defense", "2024.04.16", "60", "bullet",
     "e4 e5 Nf3 f6 Nxe5 fxe5 Qh5+ Ke7 Qxe5+ Kf7 Bc4+ Kg6 Qf5+ Kh6 d4+ g5 Qf7 "
     "Qe7 Qxe7 Bxe7"),  # resign, Samay won a queen
]


# Usernames the offline sample can serve a clone for without any network.
SAMPLE_USERNAMES = {"samayraina"}


def _render_pgn(white, black, result, eco, opening, eco_slug, date,
                time_control, moves) -> str:
    headers = [
        ("Event", "Live Chess"),
        ("Site", "Chess.com"),
        ("Date", date),
        ("White", white),
        ("Black", black),
        ("Result", result),
        ("ECO", eco),
        ("ECOUrl", f"https://www.chess.com/openings/{eco_slug}"),
        ("Opening", opening),
        ("TimeControl", time_control),
    ]
    head = "".join(f'[{k} "{v}"]\n' for k, v in headers)

    toks = moves.split()
    body_parts = []
    for i, tok in enumerate(toks):
        if i % 2 == 0:
            body_parts.append(f"{i // 2 + 1}.")
        body_parts.append(tok)
    body = " ".join(body_parts) + " " + result
    return head + "\n" + body


def _game_json(entry) -> dict:
    white, black, result, eco, opening, slug, date, tc, time_class, moves = entry
    pgn = _render_pgn(white, black, result, eco, opening, slug, date, tc, moves)
    white_res = "win" if result == "1-0" else ("checkmated" if result == "0-1" else "agreed")
    black_res = "win" if result == "0-1" else ("checkmated" if result == "1-0" else "agreed")
    return {
        "url": f"sample://game/{date}/{white}-{black}",
        "pgn": pgn,
        "time_control": tc,
        "time_class": time_class,
        "rated": True,
        "rules": "chess",
        "eco": f"https://www.chess.com/openings/{slug}",
        "end_time": 0,
        "white": {"username": white, "rating": 2100, "result": white_res},
        "black": {"username": black, "rating": 2050, "result": black_res},
    }


class SampleChessComClient:
    """Offline `ChessComSource` returning the bundled sample for `samayraina`.

    Implements the same three methods as `ChessComClient`, so the importer is
    oblivious to whether data came from the network or this fixture.
    """

    DISPLAY_NAMES = {"samayraina": "Samay Raina"}

    def get_profile(self, username: str) -> dict:
        u = username.lower()
        return {"username": u, "name": self.DISPLAY_NAMES.get(u, username)}

    def get_archives(self, username: str) -> list[str]:
        return ["sample://archive/2024/01"]

    def get_games(self, archive_url: str) -> list[dict]:
        return [_game_json(e) for e in _SAMPLE]


def sample_pgns() -> list[str]:
    """Raw PGN strings for the sample — handy for tests/validation."""
    return [_game_json(e)["pgn"] for e in _SAMPLE]
