"""PlayerStyleAnalyzer — build a style fingerprint from stored games (PHASE 3).

Reads the player's `games` and `player_moves`, replays each stored move to
recover its style features, aggregates them, and writes a `StyleProfile` row
(the five axis scores + opening preferences + a rich `style_json`).

The output `style_json` is the contract the clone engine and the DNA page both
consume, so it is intentionally explicit: headline scores, sub-metric
breakdowns, opening preferences, performance splits, and raw rates.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

import engine
from engine import from_fen
from player_clones import fen as fenutil
from player_clones.db import Database
from player_clones.models import StyleProfile
from player_clones.style_analysis import metrics
from player_clones.style_analysis.metrics import FeatureAggregate


class PlayerStyleAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def analyze(self, player_id: int, persist: bool = True) -> StyleProfile:
        games = self.db.games.for_player(player_id)
        moves = self.db.moves.for_player(player_id)

        agg = FeatureAggregate(n_games=len(games))
        per_game = defaultdict(lambda: {"castled": False, "endgame": False,
                                        "king_moves": 0})
        game_result = {g.id: g.result for g in games}

        from player_clones.pgn_parser.fast_san import match_san
        for pm in moves:
            try:
                state = from_fen(pm.fen)
                move = match_san(state, pm.move_played)
            except Exception:
                move = None
            if move is None:
                continue
            f = fenutil.extract_features(state, move, want_san=False)

            agg.n_moves += 1
            agg.checks += f.is_check
            agg.captures += f.is_capture
            agg.king_zone += f.attacks_king_zone
            agg.advances += f.advances_into_enemy
            agg.central += f.central
            agg.sacrifices += f.is_sacrifice
            agg.forks += f.creates_fork
            agg.mates += f.gives_mate
            agg.promotions += f.is_promotion
            agg.developing += f.develops_piece

            gstate = per_game[pm.game_id]
            if pm.phase == fenutil.OPENING:
                if f.is_sacrifice:
                    agg.opening_sacrifices += 1
                if f.king_move:
                    agg.opening_king_moves += 1
                    gstate["king_moves"] += 1
            if f.is_castle:
                gstate["castled"] = True
            if pm.phase == fenutil.ENDGAME:
                gstate["endgame"] = True

        # roll up per-game flags
        for gid, st in per_game.items():
            if st["castled"]:
                agg.games_castled += 1
            if st["endgame"]:
                agg.games_reached_endgame += 1
                if game_result.get(gid) == "win":
                    agg.games_won_endgame += 1

        aggression, agg_parts = metrics.aggression_score(agg)
        tactical, tac_parts = metrics.tactical_score(agg)
        risk, risk_parts = metrics.risk_score(agg)
        king_safety, ks_parts = metrics.king_safety_score(agg)
        endgame, eg_parts = metrics.endgame_score(agg)

        prefs = metrics.opening_preferences(games)
        breakdowns = metrics.performance_breakdowns(games)

        style_json = {
            "headline": {
                "aggression": aggression, "tactical": tactical, "risk": risk,
                "kingSafety": king_safety, "endgame": endgame,
            },
            "breakdown": {
                "aggression": agg_parts, "tactical": tac_parts,
                "risk": risk_parts, "kingSafety": ks_parts, "endgame": eg_parts,
            },
            "rates": {
                "moves_analyzed": agg.n_moves,
                "games_analyzed": agg.n_games,
                "check_rate": round(agg.rate("checks"), 3),
                "capture_rate": round(agg.rate("captures"), 3),
                "sacrifice_rate": round(agg.rate("sacrifices"), 3),
                "fork_rate": round(agg.rate("forks"), 3),
                "central_rate": round(agg.rate("central"), 3),
                "castle_rate": round(agg.games_castled / (agg.n_games or 1), 3),
            },
            "opening_preferences": prefs,
            "performance": breakdowns,
        }

        profile = StyleProfile(
            player_id=player_id, aggression=aggression, tactical=tactical,
            risk=risk, king_safety=king_safety, endgame=endgame,
            opening_preferences=prefs, style_json=style_json,
        )
        if persist:
            self.db.styles.upsert(profile)
        return profile
