"""
hand_strength.py — Hand-strength rework.

Preflop now returns a real Chen-percentile strength (the old version always
returned 0.5). Postflop uses the treys rank normalized to 0..1, plus simple
draw detection for semi-bluffing / implied-odds reasoning.
"""
from treys import Evaluator, Card
from src.engine.range_model import preflop_percentile, RANK_ORDER

_VAL = {r: i + 2 for i, r in enumerate(RANK_ORDER)}


class HandStrength:
    def __init__(self):
        self.evaluator = Evaluator()

    def evaluate(self, hand, board):
        if not board or len(hand) + len(board) < 5:
            return self.preflop_strength(hand)
        return self.postflop_strength(hand, board)

    def preflop_strength(self, hand):
        if not hand or len(hand) < 2:
            return 0.5
        return round(preflop_percentile(hand), 3)

    def postflop_strength(self, hand, board):
        score = self.evaluator.evaluate(board, hand)
        return 1 - (score / 7462)

    def made_class(self, hand, board):
        if not board or len(board) < 3:
            return "preflop"
        s = self.evaluator.evaluate(board, hand)
        return self.evaluator.class_to_string(self.evaluator.get_rank_class(s))

    def draws(self, hand, board):
        out = {"flush_draw": False, "oesd": False, "gutshot": False}
        if not board or len(board) < 3:
            return out
        cards = list(hand) + list(board)
        suits = [Card.int_to_str(c)[1] for c in cards]
        for s in set(suits):
            if suits.count(s) == 4:
                out["flush_draw"] = True
        vals = sorted(set(_VAL[Card.int_to_str(c)[0]] for c in cards))
        if 14 in vals:
            vals = sorted(set(vals + [1]))
        for low in range(1, 11):
            present = [v for v in range(low, low + 5) if v in vals]
            if len(present) == 4:
                missing = [v for v in range(low, low + 5) if v not in vals][0]
                if missing in (low, low + 4):
                    out["oesd"] = True
                else:
                    out["gutshot"] = True
        return out