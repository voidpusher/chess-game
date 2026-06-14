# Player Clone Engine

Play against a **style clone** of any public Chess.com player. The clone does not
try to play the strongest move — it tries to play the move the *real player* is
most likely to play.

Built as a self-contained subsystem on top of the existing chess app. It reuses
the app's `engine.py` for all chess logic (board, legality, search, SAN/FEN) and
**does not** reimplement any of it. No machine learning, no neural networks — the
clone is `existing engine candidates + transparent style ranking + real-game
repertoire mimicry`.

```python
from player_clones import create_player_clone

samay  = create_player_clone("samayraina")      # live import from Chess.com
magnus = create_player_clone("magnuscarlsen")   # live import from Chess.com
                                                # (falls back to bundled sample offline)
move   = samay.choose_move(state)               # an engine.Move
```

## Architecture

```
player_clones/
├── importer/         PHASE 1  Chess.com ingestion (PlayerImporterService)
│   ├── chesscom_client.py   live HTTP client (ChessComSource interface)
│   ├── sample_data.py       bundled offline sample + SampleChessComClient
│   └── player_importer.py   import_player / sync_player
├── pgn_parser/       PHASE 2  PGN text utils + replay -> player_moves
├── style_analysis/   PHASE 3  PlayerStyleAnalyzer + metrics (5-axis fingerprint)
├── clone_engine/     PHASE 4  CandidateProvider + MoveStyleScorer + PlayerCloneEngine
├── providers/        PHASE 5  CloneProvider, PlayerCloneProvider, SamayCloneProvider,
│                              create_player_clone() factory
├── dashboard/        PHASE 7/8 DNA page + post-game report (tkinter)
├── db.py             SQLite schema + repositories (players/games/player_moves/player_styles)
├── models.py         typed domain models
├── fen.py            FEN serialisation, phase classification, move features, SEE
├── api.py            REST-style route facade (+ optional stdlib HTTP server)
└── cli.py            command-line entry point
```

The pipeline (each stage depends only on the one above, via interfaces):

```
Chess.com archives ─▶ PlayerImporterService ─▶ games (SQLite)
                                                  │
                          PgnParser (replay) ◀────┘
                                  │
                            player_moves (FEN + phase + eval)
                                  │
                        PlayerStyleAnalyzer
                                  │
                  player_styles (aggression/tactical/risk/kingSafety/endgame)
                                  │
   live position ─▶ PlayerCloneEngine ─▶ move
                      ├─ tier 1: repertoire mimicry (play what they really played)
                      └─ tier 2: top-N engine candidates ─▶ MoveStyleScorer ─▶ pick
```

## How the clone chooses a move

1. **Repertoire mimicry.** If the live position (matched by position key over the
   player's `player_moves`) is one the real player has actually been in, play what
   they played, weighted by frequency. This reproduces real opening lines and pet
   moves verbatim.
2. **Style ranking.** Otherwise take the top-N moves from the existing engine
   (bounds quality so the clone never hangs a piece for nothing) and pick the one
   the `MoveStyleScorer` rates most characteristic of the player — checks/captures
   gated by aggression, sacrifices by risk, castling by king safety, etc. A small
   temperature keeps it from being robotic.

## Style fingerprint

Five 0–100 axes derived from transparent move-feature rates (see
`style_analysis/metrics.py`). Sacrifice detection uses **Static Exchange
Evaluation** (`fen.see_capture`) so a real piece sac for attack is distinguished
from a safely-defended capture.

## CLI

```bash
python -m player_clones.cli import samayraina            # full live import + analyze
python -m player_clones.cli import samayraina --sample    # offline bundled sample
python -m player_clones.cli sync   samayraina            # incremental refresh
python -m player_clones.cli analyze samayraina           # rebuild fingerprint
python -m player_clones.cli dna    samayraina            # print DNA as JSON
python -m player_clones.cli serve                        # run the REST API
```

## Modes

Four versions of the same clone — identical personality, different strength —
via `player_clones/modes/` (`SamayModeManager`):

| Mode | What it is | Strength |
|---|---|---|
| **Casual Samay** | Impulsive stream chess: boosted aggression/risk weights, depth-1 candidates, top-10 style picks, 28% blunder injection | ~800–1200 |
| **Real Samay** | The clone engine exactly as-is, zero adjustments | historical |
| **Peak Samay** | Depth-3 candidates, only moves within 90cp of best, near-deterministic; aggression profile unchanged | his ceiling |
| **Adaptive Samay** | `get_adaptive_samay(user_rating)` — accuracy knobs (depth, eval window, blunder rate, temperature) scale with your rating; personality untouched | ~you + 75 |

A mode is just a `ModeConfig` parameter set applied through composition
(`ModedCloneProvider` + `ModedCandidateProvider`) — no clone logic duplicated.
All modes share one base clone, so switching is instant.

## In the GUI

`app.py` gains an **Opponent** selector (`Computer` / `Samay Clone`), a
**Mode…** button (opens the mode-selection screen with descriptions + estimated
strength), and a **Samay DNA** button. Selecting the clone routes the AI move
through `PlayerCloneEngine`; finishing a game opens the post-game report headed
by the mode name ("Played Against: Casual Samay"). Nothing in the existing
gameplay path changed.

## Adding another player

No code changes — `create_player_clone("<chesscom_username>")`. For a named
convenience class, mirror `providers/samay_provider.py` (≈15 lines).

## Tests

`test_player_clones.py` (offline, deterministic) covers all phases;
`test_clone_gui.py` is a live GUI smoke test.

## Notes / limitations

- The style scores are heuristic and transparent (tunable in `metrics.py`), not
  learned. That is intentional per the brief (no ML).
- The bundled offline sample is built from classic attacking master games so the
  clone is demonstrable with zero network. Run a live `import` for a fingerprint
  from the player's real games.
- Candidate generation uses the project's own alpha-beta engine, not Stockfish
  (the app never actually bundled Stockfish); swapping in a UCI engine would mean
  implementing the same `CandidateProvider.top_moves` contract.
