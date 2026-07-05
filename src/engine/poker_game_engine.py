"""
poker_game_engine.py — Correct heads-up (1v1) No-Limit Hold'em betting engine.
"""
from treys import Deck, Evaluator

HERO = 0
BOT = 1

PREFLOP, FLOP, TURN, RIVER, SHOWDOWN, DONE = (
    "preflop", "flop", "turn", "river", "showdown", "done",
)
FOLD, CHECK, CALL, BET, RAISE = "fold", "check", "call", "bet", "raise"


class PokerGameEngine:
    def __init__(self, starting_stack=200, sb=1, bb=2):
        self.evaluator = Evaluator()
        self.starting_stack = starting_stack
        self.sb = sb
        self.bb = bb

        self.stacks = [starting_stack, starting_stack]
        self.button = HERO
        self.hand_no = 0
        self._new_hand_state()

    # ------------------------------------------------------------------ #
    def _new_hand_state(self):
        self.deck = Deck()
        self.board = []
        self.hole = [[], []]
        self.street = PREFLOP
        self.pot = 0
        self.street_commit = [0, 0]
        self.contrib = [0, 0]
        self.folded = [False, False]
        self.all_in = [False, False]
        self.has_acted = [False, False]
        self.current_bet = 0
        self.min_raise = self.bb
        self.to_act = HERO
        self.done = False
        self.result = None
        self.log = []

    def start_hand(self):
        if self.stacks[HERO] <= 0 or self.stacks[BOT] <= 0:
            self.done = True
            self.result = {"winner": "match_over"}
            return
        self.hand_no += 1
        self._new_hand_state()
        self.hole[HERO] = [self.deck.draw(1)[0], self.deck.draw(1)[0]]
        self.hole[BOT] = [self.deck.draw(1)[0], self.deck.draw(1)[0]]

        sb_player = self.button
        bb_player = self._other(self.button)
        self._post(sb_player, min(self.sb, self.stacks[sb_player]))
        self._post(bb_player, min(self.bb, self.stacks[bb_player]))
        self.current_bet = self.bb
        self.min_raise = self.bb
        self.to_act = sb_player
        self.has_acted = [False, False]
        self.log.append(f"--- Hand #{self.hand_no} | button=P{self.button} ---")

    def _post(self, p, amount):
        self.stacks[p] -= amount
        self.street_commit[p] += amount
        self.contrib[p] += amount
        if self.stacks[p] == 0:
            self.all_in[p] = True

    # ------------------------------------------------------------------ #
    def legal_actions(self):
        if self.done or self.street in (SHOWDOWN, DONE):
            return {"actions": []}
        p = self.to_act
        stack = self.stacks[p]
        to_call = max(0, min(self.current_bet - self.street_commit[p], stack))
        info = {
            "to_act": p, "to_call": to_call,
            "pot": self.pot + sum(self.street_commit),
            "stack": stack, "actions": [],
        }
        if to_call == 0:
            info["actions"].append(CHECK)
            if stack > 0:
                info["bet"] = {
                    "min_to": self.street_commit[p] + min(self.bb, stack),
                    "max_to": self.street_commit[p] + stack,
                }
        else:
            info["actions"].append(FOLD)
            info["actions"].append(CALL)
            info["call_amount"] = to_call
            if stack > to_call:
                max_to = self.street_commit[p] + stack
                min_to = min(self.current_bet + self.min_raise, max_to)
                info["actions"].append(RAISE)
                info["raise"] = {"min_to": min_to, "max_to": max_to}
        return info

    # ------------------------------------------------------------------ #
    def apply_action(self, kind, amount=None):
        if self.done:
            return
        p = self.to_act
        legal = self.legal_actions()
        acts = legal["actions"]
        stack = self.stacks[p]
        to_call = legal.get("to_call", 0)

        if kind == FOLD and FOLD in acts:
            self.folded[p] = True
            self.log.append(f"P{p} folds")
            self._end_by_fold(self._other(p))
            return
        if kind == CHECK and CHECK in acts:
            self.has_acted[p] = True
            self.log.append(f"P{p} checks")
        elif kind in (BET, RAISE) and (legal.get("raise") or legal.get("bet")):
            spec = legal.get("raise") or legal.get("bet")
            target = amount if amount is not None else spec["min_to"]
            target = int(max(spec["min_to"], min(target, spec["max_to"])))
            prev_bet = self.current_bet
            self._put(p, target - self.street_commit[p])
            raise_size = self.street_commit[p] - prev_bet
            if raise_size >= self.min_raise:
                self.min_raise = raise_size
            self.current_bet = max(self.current_bet, self.street_commit[p])
            self.has_acted = [False, False]
            self.has_acted[p] = True
            verb = "bets" if prev_bet == 0 else "raises to"
            self.log.append(f"P{p} {verb} {self.street_commit[p]}")
        elif kind == CALL and CALL in acts:
            pay = min(to_call, stack)
            self._put(p, pay)
            self.has_acted[p] = True
            self.log.append(f"P{p} calls {pay}")
        else:
            if CHECK in acts:
                self.has_acted[p] = True
            else:
                self.folded[p] = True
                self._end_by_fold(self._other(p))
                return
        self._advance_after_action()

    def _put(self, p, amount):
        amount = max(0, min(amount, self.stacks[p]))
        self.stacks[p] -= amount
        self.street_commit[p] += amount
        self.contrib[p] += amount
        if self.stacks[p] == 0:
            self.all_in[p] = True

    # ------------------------------------------------------------------ #
    def _advance_after_action(self):
        if self._round_closed():
            self._close_street()
        else:
            self.to_act = self._next_to_act(self.to_act)

    def _round_closed(self):
        contenders = [i for i in (HERO, BOT) if not self.folded[i]]
        if len(contenders) < 2:
            return True
        actionable = [i for i in contenders if not self.all_in[i]]
        if not actionable:
            return True
        for i in actionable:
            if not self.has_acted[i] or self.street_commit[i] != self.current_bet:
                return False
        return True

    def _close_street(self):
        self.pot += sum(self.street_commit)
        self.street_commit = [0, 0]
        self.current_bet = 0
        self.min_raise = self.bb
        self.has_acted = [False, False]
        if len([i for i in (HERO, BOT) if not self.folded[i]]) < 2:
            return
        if self._betting_finished():
            while len(self.board) < 5:
                self._deal_next_board()
            self.street = SHOWDOWN
            self._settle()
            return
        if self.street == PREFLOP:
            self._deal_next_board(); self.street = FLOP
        elif self.street == FLOP:
            self._deal_next_board(); self.street = TURN
        elif self.street == TURN:
            self._deal_next_board(); self.street = RIVER
        elif self.street == RIVER:
            self.street = SHOWDOWN
            self._settle()
            return
        self.to_act = self._other(self.button)

    def _betting_finished(self):
        contenders = [i for i in (HERO, BOT) if not self.folded[i]]
        if len(contenders) < 2:
            return True
        return any(self.all_in[i] for i in contenders)

    def _deal_next_board(self):
        if len(self.board) == 0:
            self.board += self.deck.draw(3)
        else:
            self.board += self.deck.draw(1)

    # ------------------------------------------------------------------ #
    def _end_by_fold(self, winner):
        self.pot += sum(self.street_commit)
        self.street_commit = [0, 0]
        self._refund_excess()
        self.stacks[winner] += self.pot
        won = self.pot
        self.pot = 0
        self.street = DONE
        self.done = True
        self.result = {"winner": self._name(winner), "reason": "fold",
                       "pot": won}
        self.log.append(f"P{winner} wins {won} (fold)")

    def _settle(self):
        self._refund_excess()
        hero = self.evaluator.evaluate(self.board, self.hole[HERO])
        bot = self.evaluator.evaluate(self.board, self.hole[BOT])
        if hero < bot:
            winner = HERO
        elif bot < hero:
            winner = BOT
        else:
            winner = None
        won = self.pot
        if winner is None:
            half = self.pot // 2
            self.stacks[HERO] += half
            self.stacks[BOT] += self.pot - half
            wname = "split"
        else:
            self.stacks[winner] += self.pot
            wname = self._name(winner)
        self.pot = 0
        self.street = DONE
        self.done = True
        self.result = {
            "winner": wname, "reason": "showdown", "pot": won,
            "hero_class": self.evaluator.class_to_string(
                self.evaluator.get_rank_class(hero)),
            "bot_class": self.evaluator.class_to_string(
                self.evaluator.get_rank_class(bot)),
        }
        self.log.append(f"showdown: {wname} wins {won}")

    def _refund_excess(self):
        called = min(self.contrib[HERO], self.contrib[BOT])
        for p in (HERO, BOT):
            excess = self.contrib[p] - called
            if excess > 0:
                self.stacks[p] += excess
                self.pot -= excess
                self.contrib[p] -= excess

    def end_hand_and_rotate(self):
        self.button = self._other(self.button)

    # ------------------------------------------------------------------ #
    def _next_to_act(self, p):
        o = self._other(p)
        return p if (self.folded[o] or self.all_in[o]) else o

    @staticmethod
    def _other(p):
        return BOT if p == HERO else HERO

    @staticmethod
    def _name(p):
        return "hero" if p == HERO else "bot"

    def position_of(self, p):
        return "BTN" if p == self.button else "BB"

    # ------------------------------------------------------------------ #
    def view_for(self, p, opponent_name="hero"):
        legal = self.legal_actions()
        return {
            "hole": self.hole[p],
            "board": self.board,
            "street": self.street,
            "pot": self.pot + sum(self.street_commit),
            "to_call": legal.get("to_call", 0),
            "stack": self.stacks[p],
            "opp_stack": self.stacks[self._other(p)],
            "position": self.position_of(p),
            "street_commit_self": self.street_commit[p],
            "legal": legal,
            "opponent_name": opponent_name,
        }