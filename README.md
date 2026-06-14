# Chess Game Python

A Python chess game with a tkinter GUI, a legal move engine, difficulty-based computer play, opening knowledge retrieval, and post-game analysis.

## Repository Contents

| File | Contents |
|---|---|
| `app.py` | tkinter desktop GUI with board rendering, legal move markers, highlights, and game controls |
| `engine.py` | Chess state, move generation, evaluation, alpha-beta search, SAN/FEN helpers, and perft validation |
| `knowledge.py` | Opening and master-game knowledge base used to retrieve book moves and commentary |
| `analysis.py` | Post-game move review with accuracy scoring, mistake categories, missed tactics, and coaching tips |
| `test_engine.py` | Engine, perft, book retrieval, AI legality, and mate-in-one validation |
| `test_analysis.py` | Game review tests for blunder and missed-mate detection |
| `test_gui.py` | GUI smoke test with simulated board clicks |
| `player_clones/` | **Player Clone Engine** — play against a style clone of any Chess.com player (see `player_clones/README.md`) |
| `test_player_clones.py` | Player-clone tests: ingestion, PGN parsing, style analysis, clone selection |
| `test_clone_gui.py` | GUI smoke test for the "Play Against Samay" mode |

## Language

Python

## Features

- Play chess against the computer in a desktop tkinter interface.
- Choose easy, medium, or hard difficulty.
- See legal move dots, capture markers, last-move highlights, and check highlights.
- Use a RAG-style chess knowledge base for opening moves and move commentary.
- Review the game with accuracy, mistake categories, an evaluation graph, and coaching tips.
- **Play Against Samay** — a style clone of Chess.com user `samayraina` (or any public
  username) that plays the move the real player is most likely to play, with a "Samay DNA"
  page and a post-game style report. See `player_clones/README.md`.

## Web App (browser frontend + REST API)

In addition to the tkinter desktop app, the project ships a web version: a Flask
REST API (`server.py`) over the same engine, with a modern browser frontend in
`frontend/`. It supports playing the classic engine **or** the Samay Raina clone
(Casual / Real / Peak modes), with live Hinglish banter, a move list, an eval
bar, and source badges (Book / Style) on every clone move.

```bash
pip install -r requirements.txt   # flask, flask-cors
python server.py                  # then open http://localhost:5000
```

### Getting the *real* Samay bot (import his Chess.com games)

Out of the box the clone falls back to a small bundled sample, so it only
approximates his style. To build the authentic bot from his real games, run a
full import once — this downloads every public game from the Chess.com API,
parses the PGN, and rebuilds his style fingerprint and opening repertoire:

```bash
python -m player_clones.cli import samayraina --full
```

This produces a local SQLite database (`player_clones/data/player_clones.db`,
several hundred MB — **gitignored**, not committed) with tens of thousands of
games. After it finishes, restart `server.py`; the clone will now play Samay's
real openings (e.g. his Sicilian as Black, English as White) as "Book" moves and
match his actual style fingerprint. The import is idempotent — rerun it (or
`python -m player_clones.cli sync samayraina`) to pull new games later.

### Deploy (Render / Railway / Fly)

The web app deploys with **no database setup**. The clone ships as a small
committed artifact — `player_clones/data/samay_book.json.gz` (~280 KB, his real
recurring repertoire + style fingerprint built from 21k games). At runtime the
server uses the full local database if present, otherwise this artifact, so it
runs anywhere without an import step.

- **Render:** New → Blueprint → connect the repo. `render.yaml` provisions a free
  web service automatically (`gunicorn server:app`).
- **Railway / others:** the `Procfile` runs the same gunicorn command.

It runs as a single gunicorn worker (the app holds the current game in memory).
To refresh the clone with newer games, run the full import locally and rebuild
the artifact:

```bash
python -m player_clones.cli import samayraina --full   # refresh local DB
python -m player_clones.book export samayraina         # rebuild the artifact
```

## Requirements

- Python 3.10 or newer
- tkinter (desktop app) — included with most standard Python installations
- `flask`, `flask-cors`, `gunicorn` (web app only) — `pip install -r requirements.txt`

The engine and desktop GUI require no third-party packages; only the web app
needs Flask.

## Run (desktop)

```bash
python app.py
```

## Test

```bash
python test_engine.py
python test_analysis.py
python test_gui.py
```

## Difficulty Levels

| Level | Behavior |
|---|---|
| Easy | 1-ply search with random noise |
| Medium | 2-ply alpha-beta search with quiescence and early opening theory |
| Hard | 3-ply alpha-beta search with quiescence, piece-square tables, and book moves |

## Notes

The GUI updates after every human move before the engine starts thinking. The engine search runs on a background thread against a copied board state, so the interface stays responsive during computer turns.
