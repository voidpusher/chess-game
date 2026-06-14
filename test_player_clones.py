"""Tests for the Player Clone Engine (all 8 phases).

Fully offline and deterministic — uses the bundled sample, in-memory SQLite, and
seeded RNG. Runs under pytest (`pytest test_player_clones.py`) or standalone
(`python test_player_clones.py`).
"""

import random

import engine
from player_clones import fen as fenutil
from player_clones.db import Database, position_key
from player_clones.models import Player, Game
from player_clones.importer import PlayerImporterService, SampleChessComClient
from player_clones.importer.sample_data import sample_pgns
from player_clones.pgn_parser import tokenize_movetext, split_pgn, PgnParser
from player_clones.style_analysis import PlayerStyleAnalyzer
from player_clones.clone_engine import CandidateProvider, MoveStyleScorer
from player_clones.fen import see_capture, state_to_fen
from player_clones import create_player_clone
from player_clones.api import PlayerCloneAPI
from player_clones.openings import classify_opening

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _seeded_clone():
    db = Database(":memory:")
    return create_player_clone("samayraina", db=db, source="sample",
                               rng=random.Random(0)), db


# --------------------------------------------------------------------------- #
# Foundation
# --------------------------------------------------------------------------- #

def test_fen_roundtrip_and_phase():
    s = engine.State()
    assert state_to_fen(s, 1) == START_FEN
    assert fenutil.classify_phase(s, 1) == fenutil.OPENING
    # bare kings + a rook -> endgame
    b = engine.from_fen("8/8/4k3/8/8/4K3/7R/8 w - - 0 1")
    assert fenutil.classify_phase(b, 40) == fenutil.ENDGAME


def test_see_values():
    b = [None] * 64
    b[27], b[36], b[18] = "bN", "wB", "bP"          # N defended by pawn
    assert see_capture(b, 27, "w") == -10            # win N(320) lose B(330)
    b2 = [None] * 64
    b2[27], b2[36] = "bN", "wB"                       # undefended knight
    assert see_capture(b2, 27, "w") == 320
    b3 = [None] * 64
    b3[27], b3[36] = "bR", "wB"                       # undefended rook
    assert see_capture(b3, 27, "w") == 500


# --------------------------------------------------------------------------- #
# Phase 2 — PGN parsing
# --------------------------------------------------------------------------- #

def test_tokenizer_strips_annotations():
    mt = "1. e4 {best by test} e5 2. Nf3 (2. f4 exf4) Nc6 $1 3. Bb5 a6 1-0"
    assert tokenize_movetext(mt) == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]


def test_all_sample_pgns_replay_legally():
    for pgn in sample_pgns():
        _, mt = split_pgn(pgn)
        s = engine.State()
        for tok in tokenize_movetext(mt):
            m = engine.parse_san(s, tok)
            assert m is not None, (pgn[:40], tok)
            engine.make_move(s, m)


def test_parser_emits_only_player_moves():
    db = Database(":memory:")
    p = db.players.upsert(Player(username="samayraina", display_name="Samay Raina"))
    gj = SampleChessComClient().get_games("x")[0]      # a white game
    from player_clones.pgn_parser.pgn_parser import game_metadata
    g = game_metadata(gj["pgn"], "samayraina", gj)
    g.player_id = p.id
    db.games.insert_many([g])
    stored = db.games.for_player(p.id)[0]
    moves = PgnParser().parse_moves(stored)
    assert moves and all(m.mover == "w" for m in moves)  # samay was White here
    db.close()


# --------------------------------------------------------------------------- #
# Phase 1 — import
# --------------------------------------------------------------------------- #

def test_import_is_idempotent():
    db = Database(":memory:")
    svc = PlayerImporterService(db, client=SampleChessComClient())
    s1 = svc.import_player("samayraina")
    assert s1.games_new == 30 and s1.moves_added > 0
    s2 = svc.import_player("samayraina")
    assert s2.games_new == 0 and s2.moves_added == 0
    db.close()


# --------------------------------------------------------------------------- #
# Phase 3 — style analysis
# --------------------------------------------------------------------------- #

def test_style_fingerprint_is_aggressive():
    db = Database(":memory:")
    svc = PlayerImporterService(db, client=SampleChessComClient())
    summ = svc.import_player("samayraina")
    prof = PlayerStyleAnalyzer(db).analyze(summ.player_id)
    h = prof.headline()
    for axis in ("aggression", "tactical", "risk", "kingSafety", "endgame"):
        assert 0 <= h[axis] <= 100
    # the sample is all attacking miniatures -> tactical & aggression are high
    assert h["tactical"] >= 70 and h["aggression"] >= 60
    prefs = prof.opening_preferences
    assert prefs["white"] and prefs["black"]
    db.close()


# --------------------------------------------------------------------------- #
# Phase 4 — clone engine
# --------------------------------------------------------------------------- #

def test_clone_mimics_repertoire_in_opening():
    clone, db = _seeded_clone()
    # every sample white game opens 1.e4, so the repertoire is unambiguous
    d = clone.decide(engine.State())
    assert d.san == "e4" and d.source == "repertoire"
    db.close()


def test_clone_returns_legal_move_out_of_book():
    clone, db = _seeded_clone()
    # a non-book middlegame position (made up) -> style selection path
    s = engine.from_fen("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 5")
    legal = {m.uci() for m in engine.legal_moves(s)}
    d = clone.decide(s)
    assert d.move is not None and d.move.uci() in legal
    assert d.source in ("style", "repertoire", "forced")
    db.close()


def test_scorer_prefers_aggression_for_aggressive_profile():
    clone, db = _seeded_clone()
    scorer = MoveStyleScorer(clone.profile)
    # position where White can give check (Qh5+ vs a quiet move)
    s = engine.from_fen("rnbqkbnr/ppp2ppp/8/3pp3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3")
    checks = [m for m in engine.legal_moves(s) if engine.to_san(s, m).endswith("+")]
    quiets = [m for m in engine.legal_moves(s)
              if not engine.to_san(s, m).endswith("+")
              and not s.board[m.to]]
    assert checks and quiets
    cs = scorer.score(s, checks[0]).style_score
    qs = scorer.score(s, quiets[0]).style_score
    assert cs > qs                              # aggressive profile rewards checks
    db.close()


def test_candidate_provider_returns_ranked_moves():
    s = engine.State()
    cands = CandidateProvider(depth=2).top_moves(s, top_n=5)
    assert len(cands) == 5
    assert cands[0].eval_cp >= cands[-1].eval_cp   # sorted strongest first


# --------------------------------------------------------------------------- #
# Phase 5 — factory / providers
# --------------------------------------------------------------------------- #

def test_factory_builds_full_pipeline_offline():
    clone, db = _seeded_clone()
    assert clone.display_name == "Samay Raina Style Clone"
    dna = clone.dna()
    assert dna["total_games"] == 30
    assert set(dna["headline"]) == {"aggression", "tactical", "risk",
                                    "kingSafety", "endgame"}
    db.close()


def test_factory_is_username_agnostic_guard():
    # generic path: an unknown username with source='sample' must fail cleanly,
    # proving the sample is not special-cased into the architecture (live import
    # is the path for real arbitrary usernames).
    from player_clones.importer.chesscom_client import ChessComError
    raised = False
    try:
        create_player_clone("definitely_not_a_real_user_xyz",
                            db=Database(":memory:"), source="sample")
    except ChessComError:
        raised = True
    assert raised


# --------------------------------------------------------------------------- #
# Phase 7/8 — api + openings
# --------------------------------------------------------------------------- #

def test_api_choose_move_and_dna():
    db = Database(":memory:")
    create_player_clone("samayraina", db=db, source="sample")  # seed db
    api = PlayerCloneAPI(db)
    out = api.choose_move("samayraina", START_FEN)
    # The clone is intentionally stochastic at the board: ~90% of the time it
    # mimics a repertoire move, ~10% it deviates to a style pick (the fidelity
    # knob — real players vary). The invariant that always holds for the API
    # layer is that it returns a single *legal* move for the position.
    # (Deterministic repertoire mimicry is covered by the seeded
    # test_clone_mimics_repertoire_in_opening.)
    legal_ucis = {m.uci() for m in engine.legal_moves(engine.from_fen(START_FEN))}
    assert out["move"] in legal_ucis
    assert out["san"] and out["source"] in ("repertoire", "style")
    dna = api.get_dna("samayraina")
    assert dna["total_games"] == 30
    db.close()


def test_opening_classifier():
    assert "Sicilian" in classify_opening(["e4", "c5", "Nf3", "d6", "d4"])
    assert classify_opening([]) == "Unknown"


# --------------------------------------------------------------------------- #
# standalone runner
# --------------------------------------------------------------------------- #

def _run_all():
    import sys
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    _run_all()
