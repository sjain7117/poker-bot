import random


class FrequencyPriorEngine:

    def __init__(self):

        # baseline mixed frequencies (approx poker equilibrium style)
        self.strategy_table = {
            "preflop": {
                "value": 0.55,
                "call": 0.25,
                "bluff": 0.10,
                "fold": 0.10
            },
            "flop": {
                "value": 0.45,
                "call": 0.20,
                "bluff": 0.25,
                "fold": 0.10
            },
            "turn": {
                "value": 0.50,
                "call": 0.20,
                "bluff": 0.20,
                "fold": 0.10
            },
            "river": {
                "value": 0.60,
                "call": 0.15,
                "bluff": 0.10,
                "fold": 0.15
            }
        }

    # -------------------------
    # GET STAGE
    # -------------------------
    def get_stage(self, board):

        if len(board) == 0:
            return "preflop"
        elif len(board) == 3:
            return "flop"
        elif len(board) == 4:
            return "turn"
        else:
            return "river"

    # -------------------------
    # MIXED NASH ACTION PICK
    # -------------------------
    def sample_action(self, board, strength_modifier=0.0):

        stage = self.get_stage(board)

        strat = self.strategy_table[stage]

        # apply slight exploit adjustment
        weights = strat.copy()

        # strength shifts equilibrium slightly
        if strength_modifier > 0.2:
            weights["value"] += 0.10
            weights["bluff"] -= 0.05

        elif strength_modifier < -0.2:
            weights["bluff"] += 0.10
            weights["value"] -= 0.05

        # normalize
        total = sum(weights.values())
        for k in weights:
            weights[k] /= total

        # sample
        r = random.random()
        cumulative = 0

        for action, prob in weights.items():
            cumulative += prob
            if r <= cumulative:
                return action

        return "call"