"""
equity_engine.py — Monte Carlo equity, now range-aware.

Backwards compatible: calculate(hand, board) still returns a dict with
"equity" vs a random opponent hand. New optional `weight_fn` weights the
sampled opponent hand by a preflop range (see range_model.range_weight_fn),
which is what makes the bot's equity "range-based" instead of vs any two cards.
"""
import random
from treys import Deck, Evaluator
from src.engine.range_model import hand_code

_FULL_DECK = Deck.GetFullDeck()


class EquityEngine:
    def __init__(self, simulations=500):
        self.simulations = simulations
        self.evaluator = Evaluator()

    def convert(self, cards):
        return cards

    def calculate(self, hand, board, weight_fn=None, simulations=None,
                  seed=None):
        if not hand or len(hand) < 2:
            return {"equity": 0.5, "wins": 0, "ties": 0, "simulations": 0}
        n = simulations or self.simulations
        rng = random.Random(seed)
        known = set(hand) | set(board)
        available = [c for c in _FULL_DECK if c not in known]

        wins = ties = total = 0
        attempts = 0
        max_attempts = n * 6
        while total < n and attempts < max_attempts:
            attempts += 1
            rng.shuffle(available)
            opp = [available[0], available[1]]
            if weight_fn is not None:
                w = weight_fn(hand_code(opp))
                if w <= 0 or rng.random() > w:
                    continue
            idx = 2
            sim_board = list(board)
            while len(sim_board) < 5:
                sim_board.append(available[idx]); idx += 1
            hero = self.evaluator.evaluate(sim_board, hand)
            oppv = self.evaluator.evaluate(sim_board, opp)
            if hero < oppv:
                wins += 1
            elif hero == oppv:
                ties += 1
            total += 1

        equity = (wins + 0.5 * ties) / total if total else 0.5
        return {"equity": equity, "wins": wins, "ties": ties,
                "simulations": total}