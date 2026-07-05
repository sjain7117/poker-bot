"""
rule_bot.py — The decision engine ("RuleBot"), rebuilt to play the opponent.
Orchestrates every property module through one coherent pipeline, adapts to the
opponent's measured style in real time, and returns a concrete action WITH a
bet amount, sized and clamped to legal.
"""
import math
import random

from src.engine.equity_engine import EquityEngine
from src.engine.fold_equity import FoldEquityEngine
from src.engine.position import PositionEngine
from src.engine.ev_calibration import EVCalibrationEngine
from src.engine.bluff_control import BluffControlEngine
from src.engine.hand_strength import HandStrength
from src.engine.opponent_model import OpponentModel
from src.engine.range_model import RangeModel, range_weight_fn
from src.engine.nash_equilibrium import NashEquilibriumEngine
from src.engine.mixed_strategy import MixedStrategyEngine
from src.engine.meta_game import MetaGameEngine
from src.engine.opponent_exploitation import OpponentExploitationEngine
from src.engine.reinforcement_learning import ReinforcementLearningEngine
from src.engine.thinking_ahead import ThinkingAheadEngine
from src.engine.bet_sizing import BetSizingEngine

SOFTMAX_TEMP = 0.9
VALUE_EQUITY = 0.55
BLUFF_EQUITY = 0.45
BLUFF_CAP = {"preflop": 0.30, "flop": 0.38, "turn": 0.30, "river": 0.24}


class RuleBot:
    def __init__(self, name="RuleBot", seed=None):
        self.name = name
        self.rng = random.Random(seed)

        self.equity_engine = EquityEngine(simulations=240)
        self.fold_equity = FoldEquityEngine()
        self.position_engine = PositionEngine()
        self.ev_engine = EVCalibrationEngine()
        self.bluff_control = BluffControlEngine()
        self.hand_strength = HandStrength()
        self.range_model = RangeModel()
        self.nash = NashEquilibriumEngine()
        self.mixed = MixedStrategyEngine()
        self.meta = MetaGameEngine()
        self.exploitation = OpponentExploitationEngine()
        self.rl = ReinforcementLearningEngine()
        self.thinking_ahead = ThinkingAheadEngine()
        self.bet_sizing = BetSizingEngine()

        self.opponents = {}
        self._rl_pending = []

    # ------------------------------------------------------------------ #
    def opponent(self, name):
        if name not in self.opponents:
            self.opponents[name] = OpponentModel(name)
        return self.opponents[name]

    def observe_opponent_action(self, name, action, street):
        self.opponent(name).update(action, street)
        self.exploitation.update(name, action, street)

    def new_hand(self, name="hero"):
        self.opponent(name).new_hand()

    def settle_hand(self, reward):
        for state, tag in self._rl_pending:
            self.rl.update(state, tag, reward)
        self._rl_pending.clear()

    # ------------------------------------------------------------------ #
    def decide(self, hand_or_view, board=None, pot=10, call_cost=2,
               opponent_name="hero"):
        view = (hand_or_view if isinstance(hand_or_view, dict)
                else self._legacy_view(hand_or_view, board, pot, call_cost,
                                       opponent_name))
        try:
            return self._decide(view)
        except Exception as e:
            kind = "check" if view.get("to_call", 0) == 0 else "fold"
            return self._format(kind, None, 0.0, 0.0, f"safe fallback: {e}", {})

    # ------------------------------------------------------------------ #
    def _decide(self, view):
        hole = view["hole"]; board = view["board"]; street = view["street"]
        pot = view["pot"]; to_call = view["to_call"]
        stack = view["stack"]; opp_stack = view["opp_stack"]
        position = view["position"]; legal = view["legal"]
        commit = view["street_commit_self"]; name = view.get("opponent_name", "hero")
        opp = self.opponent(name)

        # ---- opponent profile: play the player, not just the cards ----
        prof = opp.profile()
        aggr = 0 if to_call <= 0 else (2 if to_call >= 0.7 * max(1, pot) else 1)

        # Range the opponent has RIGHT NOW. Facing a bet, a habitual aggressor
        # is betting wide (don't fold), a passive player is betting narrow
        # (respect it). When we're first to act, use their general continue
        # range for value/bluff planning.
        if to_call > 0:
            frac = self.range_model.villain_bet_frac(
                prof["aggression"], aggr, prof["confidence"], opp.leaks)
        else:
            frac = self.range_model.style_to_frac(opp.style, 0, opp.leaks)
        wf = range_weight_fn(frac)
        sims = 150 if street == "preflop" else 240
        equity = self.equity_engine.calculate(
            hole, board, weight_fn=wf, simulations=sims,
            seed=self.rng.random())["equity"]

        hs = self.hand_strength.evaluate(hole, board)
        draws = self.hand_strength.draws(hole, board)

        # Fold equity when WE bet = how often this specific opponent folds,
        # blended with the board-texture model. A station never folds; an
        # over-folder folds constantly.
        fe_model = self.fold_equity.estimate(opp, board)
        fold_prob = (prof["confidence"] * prof["fold_tendency"]
                     + (1 - prof["confidence"]) * fe_model)
        fold_prob = max(0.03, min(0.9, fold_prob))

        # ---- higher-level reads --------------------------------------
        ta = self.thinking_ahead.evaluate_line(equity, hs, fold_prob,
                                               opp.style, pot, aggr)
        base_line = ta["best_line"]                       # value / bluff / trap
        line = self.mixed.choose_line(base_line, equity, fold_prob,
                                      position, opp.leaks)
        meta = self.meta.get_profile(name)
        rl_state = self.rl.encode_state(equity, hs, position, opp.style)
        rl_adj = self.rl.get_adjustment(rl_state)
        exploit = self.exploitation.exploit_score(name)
        pos_mod = self.position_engine.strategy_modifier(position)
        stage = self.nash.get_stage(board)
        nash_freq = self.nash.strategy_table.get(stage, self.nash.strategy_table["flop"])
        realize = self._realize(position, street, draws)

        # ---- candidate actions with EV -------------------------------
        cands = self._candidates(view, equity, realize, draws, hs, fold_prob)
        weights = self._softmax([c["ev"] for c in cands], SOFTMAX_TEMP)

        # ---- blend priors + exploits + adaptation --------------------
        # Profile-driven exploitation: fold_tendency drives bluffing, and a
        # station kills bluffs while boosting value. Confidence scales how hard
        # we lean on these reads.
        cf = prof["confidence"]
        bluff_mult = 1.0 + cf * (prof["fold_tendency"] - 0.35) * 2.2
        value_mult = 1.0 + cf * (0.55 - prof["fold_tendency"]) * 1.2
        if "CALLING_STATION" in opp.leaks:
            bluff_mult *= 0.25; value_mult *= 1.35
        if prof["maniac"]:
            value_mult *= 1.15                 # they pay off; get value
        blended = []
        for c, w in zip(cands, weights):
            tag = c["tag"]
            m = 1.0
            m *= 1.0 + 0.6 * nash_freq.get(self._nash_key(tag), 0.1)   # Nash prior
            if self._line_matches(tag, line):
                m *= 1.5                                               # mixed-strategy line
            if tag == "bluff":
                m *= max(0.4, 1.0 - meta["bluff_penalty"])            # meta-game
                m *= 1.0 + rl_adj["bluff_bias"]                        # RL
                m *= 1.0 + max(-0.4, exploit)                          # exploitation
                m *= 1.0 + pos_mod["bluff_bias"]                       # position
                m *= max(0.1, bluff_mult)                              # opponent fold tendency
            elif tag == "value":
                m *= 1.0 + meta["value_bonus"]
                m *= 1.0 + rl_adj["value_bias"]
                m *= 1.0 + max(0.0, exploit)
                m *= 1.0 + pos_mod["value_bias"]
                m *= max(0.4, value_mult)
            elif tag == "trap":
                m *= 1.0 + meta["aggression_shift"]
                if prof["maniac"]:
                    m *= 1.6                     # let the maniac bet for us
            elif tag == "fold":
                m *= 1.0 + rl_adj["fold_bias"]
            m *= self._leak_multiplier(tag, opp.leaks)                # leaks
            blended.append(max(1e-6, w * m))

        # Preflop discipline: fold the worst hands to a raise — but defend
        # much wider against a habitual raiser (their range is junky, so
        # over-folding just lets them run us over). Fold hard only vs players
        # who raise a credible (tight) range.
        if street == "preflop" and to_call > 0:
            credible = 1.0 - min(0.85, prof["aggression"] * prof["confidence"])
            trash_line = 0.15 * credible          # maniac -> tiny/no fold zone
            if hs < trash_line:
                for i, c in enumerate(cands):
                    if c["kind"] == "fold":
                        blended[i] *= 4.0
                    elif c["kind"] in ("call", "bet", "raise"):
                        blended[i] *= 0.5

        blended = self._cap_bluffs(cands, blended, BLUFF_CAP.get(street, 0.3))
        blended = self._apply_trap(cands, blended, equity, hs, to_call, opp)

        total = sum(blended)
        probs = [b / total for b in blended]
        chosen = cands[self._sample(probs)]

        # ---- pot-odds safety net -------------------------------------
        # Never fold when equity clearly beats the price. If sampling picked
        # fold but calling is plainly +EV (equity comfortably above pot odds),
        # override to the call. This is the discipline that stops the bot from
        # spewing folds to big bets when it's actually ahead.
        if chosen["kind"] == "fold" and to_call > 0:
            pot_odds_need = to_call / max(1, pot + to_call)
            eff = max(equity, equity + self._draw_bonus(draws))
            if eff >= pot_odds_need + 0.04:
                call_c = next((c for c in cands if c["kind"] == "call"), None)
                strong_raise = next((c for c in cands if c["kind"] == "raise"
                                     and c["tag"] == "value"), None)
                if eff >= 0.70 and strong_raise and self.rng.random() < 0.5:
                    chosen = strong_raise
                elif call_c:
                    chosen = call_c

        amount = self._final_amount(chosen, view, equity, hs, fold_prob)

        self._rl_pending.append((rl_state, chosen["tag"]))
        if chosen["tag"] == "bluff":
            self.bluff_control.register_bluff(self.opponent(name).hands_played)

        pot_odds = to_call / max(1, pot + to_call)
        debug = {
            "equity": round(equity, 3), "hand_strength": round(hs, 3),
            "opp_style": opp.style, "leaks": list(opp.leaks),
            "line": line, "best_line": base_line, "range_frac": round(frac, 2),
            "fold_equity": round(fold_prob, 2), "position": position,
            "aggression": round(prof["aggression"], 2),
        }
        return self._format(chosen["kind"], amount, equity, pot_odds,
                            chosen["reason"], debug)

    # ------------------------------------------------------------------ #
    def _candidates(self, view, e, realize, draws, hs, fold_prob):
        pot = view["pot"]; to_call = view["to_call"]
        commit = view["street_commit_self"]; legal = view["legal"]
        cands = []
        db = self._draw_bonus(draws)

        if to_call == 0:
            cands.append({"kind": "check", "amount": None, "tag": "passive",
                          "ev": realize * e * pot, "reason": "check"})
            if "bet" in legal:
                for f in (0.5, 0.85, 1.3):
                    c = self._bet_candidate(view, e, realize, pot, commit, f, db)
                    if c:
                        cands.append(c)
        else:
            cands.append({"kind": "fold", "amount": None, "tag": "fold",
                          "ev": 0.0, "reason": "fold"})
            implied = self._implied(draws, view)
            # A call is "terminal" when it closes the action (someone is all-in)
            # or it's the river — then you see every remaining card and realize
            # 100% of your equity. Discounting those calls made the bot fold
            # hands it was a clear favourite with.
            street = view["street"]
            terminal = (to_call >= view["stack"] or view["opp_stack"] <= 0
                        or street == "river")
            call_realize = 1.0 if terminal else max(0.90, realize + 0.12)
            eff_e = min(1.0, e + (self._draw_bonus(draws) if not terminal else 0))
            ev_call = call_realize * eff_e * (pot + to_call) - to_call + implied
            cands.append({"kind": "call", "amount": None, "tag": "call",
                          "ev": ev_call, "reason": "call"})
            if "raise" in legal:
                for f in (0.7, 1.1):
                    c = self._raise_candidate(view, e, realize, pot, to_call,
                                              commit, f, db)
                    if c:
                        cands.append(c)
                # Only offer a full stack-off when genuinely strong.
                if max(e, e + db) >= 0.72:
                    allin = legal["raise"]["max_to"]
                    c = self._raise_ev(view, e, realize, pot, to_call, commit,
                                       allin, db, fold_prob)
                    if c:
                        cands.append(c)
        return cands

    def _bet_candidate(self, view, e, realize, pot, commit, frac, db):
        spec = view["legal"]["bet"]
        target = int(max(spec["min_to"], min(commit + int(frac * pot),
                                             spec["max_to"])))
        S = target - commit
        if S <= 0:
            return None
        fe = self.fold_equity.estimate(self.opponent(view.get("opponent_name",
                                       "hero")), view["board"])
        realize2 = min(1.0, realize + 0.1)
        ev = fe * pot + (1 - fe) * (realize2 * e * (pot + 2 * S) - S)
        tag = self._tag(max(e, e + db))
        return {"kind": "bet", "amount": target, "tag": tag, "ev": ev,
                "reason": f"{tag} bet {int(frac*100)}% pot"}

    def _raise_candidate(self, view, e, realize, pot, to_call, commit, frac, db):
        spec = view["legal"]["raise"]
        target = int(max(spec["min_to"], min(commit + to_call + int(frac * (pot + to_call)),
                                             spec["max_to"])))
        fe = self.fold_equity.estimate(self.opponent(view.get("opponent_name",
                                       "hero")), view["board"])
        return self._raise_ev(view, e, realize, pot, to_call, commit, target,
                              db, fe)

    def _raise_ev(self, view, e, realize, pot, to_call, commit, target, db, fe):
        S = target - commit
        if S <= to_call:
            return None
        realize2 = min(1.0, realize + 0.1)
        raise_extra = S - to_call
        ev = fe * pot + (1 - fe) * (realize2 * e * (pot + S + raise_extra) - S)
        tag = self._tag(max(e, e + db))
        return {"kind": "raise", "amount": target, "tag": tag, "ev": ev,
                "reason": f"{tag} raise"}

    def _final_amount(self, chosen, view, e, hs, fold_prob):
        if chosen["kind"] not in ("bet", "raise"):
            return None
        legal = view["legal"]
        spec = legal.get("raise") or legal.get("bet")
        is_bluff = chosen["tag"] == "bluff"
        size = self.bet_sizing.get_bet_size(e, view["pot"], hs, fold_prob,
                                            is_bluff=is_bluff)
        commit = view["street_commit_self"]
        if chosen["kind"] == "bet":
            target = commit + max(1, int(size))
        else:
            target = commit + view["to_call"] + max(1, int(size))
        if size <= 0 and chosen.get("amount"):
            target = chosen["amount"]
        return int(max(spec["min_to"], min(target, spec["max_to"])))

    # ------------------------------------------------------------------ #
    def _tag(self, eff_e):
        if eff_e >= VALUE_EQUITY:
            return "value"
        if eff_e < BLUFF_EQUITY:
            return "bluff"
        return "value"

    @staticmethod
    def _nash_key(tag):
        return {"value": "value", "trap": "value", "bluff": "bluff",
                "call": "call", "passive": "call", "fold": "fold"}.get(tag, "call")

    @staticmethod
    def _line_matches(tag, line):
        if line in ("value", "bluff", "trap"):
            return tag == line or (line == "trap" and tag == "passive")
        if line == "call":
            return tag in ("call", "passive")
        if line == "fold":
            return tag == "fold"
        return False

    @staticmethod
    def _leak_multiplier(tag, leaks):
        m = 1.0
        if "CALLING_STATION" in leaks:
            if tag == "bluff": m *= 0.4
            if tag == "value": m *= 1.4
        if "OVERFOLDING" in leaks and tag == "bluff":
            m *= 1.6
        if "NIT" in leaks and tag == "bluff":
            m *= 1.4
        if "OVERAGGRESSIVE" in leaks and tag in ("trap", "passive"):
            m *= 1.4
        return m

    def _realize(self, position, street, draws):
        base = 0.90 if position == "BTN" else 0.78
        if street == "river":
            base = 1.0
        if draws["flush_draw"] or draws["oesd"]:
            base = min(1.0, base + 0.05)
        return base

    def _draw_bonus(self, draws):
        return (0.18 if draws["flush_draw"] else 0) + \
               (0.16 if draws["oesd"] else 0) + (0.06 if draws["gutshot"] else 0)

    def _implied(self, draws, view):
        b = self._draw_bonus(draws)
        if b <= 0:
            return 0.0
        return b * 0.15 * math.sqrt(max(1, min(view["stack"], view["opp_stack"])))

    def _apply_trap(self, cands, weights, e, hs, to_call, opp):
        if to_call != 0 or e < 0.85:
            return weights
        trap_p = 0.55 if opp.style in ("LOOSE_AGGRESSIVE", "TIGHT_AGGRESSIVE") else 0.35
        out = list(weights)
        for i, c in enumerate(cands):
            if c["kind"] in ("bet", "raise") and c["tag"] == "value":
                moved = out[i] * trap_p
                out[i] -= moved
                for j, cc in enumerate(cands):
                    if cc["kind"] in ("check", "call"):
                        out[j] += moved
                        break
        return out

    def _cap_bluffs(self, cands, weights, cap):
        total = sum(weights)
        if total <= 0:
            return weights
        bluff = sum(w for c, w in zip(cands, weights) if c["tag"] == "bluff")
        if bluff / total <= cap:
            return weights
        scale = cap / (bluff / total)
        return [w * scale if c["tag"] == "bluff" else w
                for c, w in zip(cands, weights)]

    @staticmethod
    def _softmax(xs, temp):
        if not xs:
            return []
        m = max(xs)
        ex = [math.exp((x - m) / max(1e-6, temp)) for x in xs]
        s = sum(ex)
        return [e / s for e in ex]

    def _sample(self, probs):
        r = self.rng.random(); acc = 0.0
        for i, p in enumerate(probs):
            acc += p
            if r <= acc:
                return i
        return len(probs) - 1

    def _legacy_view(self, hand, board, pot, call_cost, opponent_name):
        board = board or []
        street = {0: "preflop", 3: "flop", 4: "turn"}.get(len(board), "river")
        to_call = call_cost
        stack = 100
        if to_call == 0:
            legal = {"actions": ["check", "bet"],
                     "bet": {"min_to": 2, "max_to": stack}}
        else:
            legal = {"actions": ["fold", "call", "raise"], "call_amount": to_call,
                     "raise": {"min_to": to_call * 2, "max_to": stack}}
        return {"hole": hand, "board": board, "street": street, "pot": pot,
                "to_call": to_call, "stack": stack, "opp_stack": stack,
                "position": "BTN", "legal": legal, "street_commit_self": 0,
                "opponent_name": opponent_name}

    def _format(self, kind, amount, equity, pot_odds, reason, debug):
        return {
            "player": self.name,
            "action": kind,
            "amount": amount,
            "equity": round(float(equity), 3),
            "pot_odds": round(float(pot_odds), 3),
            "reason": reason,
            "debug": debug,
        }