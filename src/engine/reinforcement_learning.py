import random


class ReinforcementLearningEngine:

    def __init__(self):

        # -------------------------
        # STATE VALUE MEMORY
        # -------------------------
        self.memory = {}

    # -------------------------
    # STATE ENCODING
    # -------------------------
    def encode_state(self, equity, hand_strength, position, opponent_style):

        return (
            round(equity, 1),
            round(hand_strength, 1),
            position,
            opponent_style
        )

    # -------------------------
    # UPDATE AFTER HAND RESULT
    # -------------------------
    def update(self, state, action, reward):

        if state not in self.memory:
            self.memory[state] = {
                "value": 0.0,
                "count": 0
            }

        entry = self.memory[state]

        # simple running value estimate
        entry["value"] = (
            entry["value"] * entry["count"] + reward
        ) / (entry["count"] + 1)

        entry["count"] += 1

    # -------------------------
    # GET BEST ACTION SHIFT
    # -------------------------
    def get_adjustment(self, state):

        if state not in self.memory:
            return {
                "bluff_bias": 0.0,
                "value_bias": 0.0,
                "fold_bias": 0.0
            }

        value = self.memory[state]["value"]

        # -------------------------
        # POSITIVE EV SITUATIONS
        # -------------------------
        if value > 0.5:
            return {
                "bluff_bias": 0.05,
                "value_bias": 0.10,
                "fold_bias": -0.05
            }

        # -------------------------
        # NEGATIVE EV SITUATIONS
        # -------------------------
        elif value < 0.3:
            return {
                "bluff_bias": -0.10,
                "value_bias": -0.05,
                "fold_bias": 0.10
            }

        # neutral
        return {
            "bluff_bias": 0.0,
            "value_bias": 0.0,
            "fold_bias": 0.0
        }