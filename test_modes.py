"""Tests for the Samay mode system (Casual / Real / Peak / Adaptive).

Offline + deterministic: bundled sample, in-memory SQLite, seeded RNG.
Runs under pytest or standalone (`python test_modes.py`).
"""

import random

import engine
from engine import Move
from player_clones.db import Database
from player_clones.clone_engine.candidate_provider import Candidate
from player_clones.modes import (
    CASUAL, REAL, PEAK, adaptive_config, ModedCandidateProvider,
    SamayModeManager,
)
from player_clones.modes.moded_provider import scaled_profile


def _manager():
    db = Database(":memory:")
    return SamayModeManager(db=db, source="sample", rng=random.Random(3)), db


# --------------------------------------------------------------------------- #
# Configs
# --------------------------------------------------------------------------- #

def test_real_mode_is_engine_defaults():
    # REAL must equal the clone engine's own defaults — sound, authentic chess
    import inspect
    from player_clones.clone_engine.clone_engine import PlayerCloneEngine
    engine_default_window = inspect.signature(
        PlayerCloneEngine.__init__).parameters["sanity_window_cp"].default
    assert (REAL.depth, REAL.quiesce) == (3, True)
    assert (REAL.top_n, REAL.temperature, REAL.repertoire_fidelity) == (20, 0.35, 0.9)
    assert REAL.eval_window_cp == engine_default_window == 130
    assert REAL.blunder_rate == 0.0
    assert REAL.style_scale == {}


def test_casual_is_wilder_and_weaker():
    assert CASUAL.depth < REAL.depth
    assert CASUAL.eval_window_cp is None           # no sanity floor: pure chaos
    assert CASUAL.blunder_rate > 0 and CASUAL.temperature > REAL.temperature
    assert CASUAL.style_scale["risk"] > 1 and CASUAL.style_scale["aggression"] > 1
    assert CASUAL.top_n == 10                      # top 10 style-ranked moves


def test_peak_is_sharper_with_authentic_personality():
    assert PEAK.depth >= REAL.depth
    assert PEAK.eval_window_cp < REAL.eval_window_cp   # tighter accuracy floor
    assert PEAK.blunder_rate == 0.0
    assert PEAK.temperature < REAL.temperature
    assert PEAK.style_scale == {}                  # aggression profile unchanged


def test_adaptive_scales_with_rating():
    weak, mid, strong = adaptive_config(600), adaptive_config(1500), adaptive_config(2100)
    assert weak.depth <= mid.depth <= strong.depth
    assert weak.blunder_rate > mid.blunder_rate > strong.blunder_rate
    assert weak.temperature > strong.temperature
    assert (mid.eval_window_cp or 10**9) > (strong.eval_window_cp or 0)
    # style untouched at every level — personality is constant
    for cfg in (weak, mid, strong):
        assert cfg.style_scale == {}
    assert "675" in weak.strength                  # 600 + 75 target


# --------------------------------------------------------------------------- #
# Accuracy filter
# --------------------------------------------------------------------------- #

class _FakeBase:
    """Canned candidate list: evals 50, 0, -80, -300 (losses 0/50/130/350)."""
    def __init__(self):
        self.cands = [
            Candidate(move=Move(52, 36, "wP"), san="e4", eval_cp=50),
            Candidate(move=Move(51, 35, "wP"), san="d4", eval_cp=0),
            Candidate(move=Move(57, 42, "wN"), san="Nc3", eval_cp=-80),
            Candidate(move=Move(50, 34, "wP"), san="c4", eval_cp=-300),
        ]

    def top_moves(self, state, top_n=20):
        return self.cands[:top_n]


def test_sanity_window_keeps_style_among_sound_moves():
    # The engine's sanity floor: style ranking only sees near-best candidates.
    from player_clones.models import StyleProfile
    from player_clones.clone_engine.clone_engine import PlayerCloneEngine
    profile = StyleProfile(player_id=0, aggression=62, tactical=46, risk=69,
                           king_safety=77, endgame=53)
    eng = PlayerCloneEngine(profile, candidate_provider=_FakeBase(),
                            sanity_window_cp=70, temperature=0.0,
                            rng=random.Random(1))
    for _ in range(8):
        d = eng.decide(engine.State())
        assert d.san in ("e4", "d4"), d.san        # Nc3 (-80) / c4 (-300) filtered

    # window off (Casual): the weak moves are back in play for style to grab
    wild = PlayerCloneEngine(profile, candidate_provider=_FakeBase(),
                             sanity_window_cp=None, temperature=0.0,
                             rng=random.Random(1))
    seen = {wild.decide(engine.State()).san for _ in range(12)}
    assert seen - {"e4", "d4"}, "expected weak moves to be reachable when wild"


def test_blunder_injection_forces_weaker_band():
    from dataclasses import replace
    cfg = replace(CASUAL, blunder_rate=1.0)        # blunder every time
    prov = ModedCandidateProvider(cfg, rng=random.Random(1), base=_FakeBase())
    kept = prov.top_moves(engine.State(), 20)
    losses = [50 - c.eval_cp for c in kept]
    assert losses and all(120 <= l <= 700 for l in losses)   # the human-blunder band
    assert "e4" not in [c.san for c in kept]       # best move was discarded


def test_no_blunder_available_means_no_blunder():
    from dataclasses import replace
    cfg = replace(CASUAL, blunder_rate=1.0)

    class _Tight(_FakeBase):
        def __init__(self):
            self.cands = [Candidate(Move(52, 36, "wP"), "e4", 50),
                          Candidate(Move(51, 35, "wP"), "d4", 20)]
    prov = ModedCandidateProvider(cfg, rng=random.Random(1), base=_Tight())
    kept = prov.top_moves(engine.State(), 20)
    assert [c.san for c in kept] == ["e4", "d4"]   # nothing in the band — play on


# --------------------------------------------------------------------------- #
# Manager + providers
# --------------------------------------------------------------------------- #

def test_manager_spec_interface():
    mgr, db = _manager()
    assert mgr.get_casual_samay().display_name == "Casual Samay"
    assert mgr.get_real_samay().display_name == "Real Samay"
    assert mgr.get_peak_samay().display_name == "Peak Samay"
    assert mgr.get_adaptive_samay(1000).display_name == "Adaptive Samay"
    # camelCase aliases, verbatim per spec
    assert mgr.getCasualSamay().display_name == "Casual Samay"
    assert mgr.getAdaptiveSamay(1500).mode.key == "adaptive"
    try:
        mgr.get("nonsense")
        assert False, "expected KeyError"
    except KeyError:
        pass
    db.close()


def test_modes_share_base_and_report_real_dna():
    mgr, db = _manager()
    base = mgr.base()
    casual, peak = mgr.get_casual_samay(), mgr.get_peak_samay()
    # personality emphasis only in casual; peak keeps the authentic numbers
    assert casual.profile.risk >= base.profile.risk
    assert casual.profile.aggression >= base.profile.aggression
    assert peak.profile.headline() == base.profile.headline()
    # the DNA page always shows the real player, whatever the mode
    assert casual.dna() == base.dna() == peak.dna()
    db.close()


def test_every_mode_plays_legal_moves():
    mgr, db = _manager()
    fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 5"
    for prov in (mgr.get_casual_samay(), mgr.get_real_samay(),
                 mgr.get_peak_samay(), mgr.get_adaptive_samay(900)):
        s = engine.from_fen(fen)
        legal = {m.uci() for m in engine.legal_moves(s)}
        d = prov.decide(s)
        assert d.move is not None and d.move.uci() in legal, prov.display_name
    db.close()


def test_peak_takes_the_hanging_queen():
    mgr, db = _manager()
    peak = mgr.get_peak_samay()
    # black queen hangs on h4 (Nf3 attacks h4); Peak's eval window forces near-best
    s = engine.from_fen("rnb1kbnr/pppp1ppp/8/4p3/7q/5N2/PPPPPPPP/RNBQKB1R w KQkq - 0 3")
    d = peak.decide(s)
    assert d.san == "Nxh4" or (d.eval_cp is not None and d.eval_cp > 400), \
        f"Peak played {d.san} (eval {d.eval_cp})"
    db.close()


# --------------------------------------------------------------------------- #
# Personality / essence
# --------------------------------------------------------------------------- #

def test_commentator_reacts_to_events():
    from player_clones.personality import SamayCommentator
    c = SamayCommentator("real", rng=random.Random(0))
    assert c.game_start()
    # sacrifice beats everything else in priority
    line = c.on_clone_move("Bxh7", "style", {"sacrifice": 1.0, "check": 0.5}, 50)
    assert "Bxh7" in line
    # eval jumping our way reads as a user blunder
    c._prev_eval = 0
    blunder_line = c.on_clone_move("Qxd8", "style", {}, 400)
    assert "Qxd8" in blunder_line
    # repertoire move gets repertoire flavour when nothing tactical happened
    c2 = SamayCommentator("peak", rng=random.Random(1))
    rep = c2.on_clone_move("e4", "repertoire", {"repertoire": 1.0}, None)
    assert "e4" in rep
    # game-over lines for all three outcomes
    assert c.on_game_over(True) and c.on_game_over(False) and c.on_game_over(None)


def test_commentator_modes_have_flavour():
    from player_clones.personality import SamayCommentator, LINES, _MODE_EXTRA
    # every referenced event pool exists and every line is non-empty
    for event, lines in LINES.items():
        assert lines and all(isinstance(l, str) and l for l in lines), event
    for mode, extra in _MODE_EXTRA.items():
        for event, lines in extra.items():
            assert event in LINES and lines, (mode, event)
    # no repeats back-to-back
    c = SamayCommentator("casual", rng=random.Random(2))
    a = c.on_clone_move("e4", "style", {}, 0)
    b = c.on_clone_move("d4", "style", {}, 0)
    assert a.replace("e4", "") != b.replace("d4", "")


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
