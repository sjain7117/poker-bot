import math


class MetaGameEngine:

    def __init__(self):

        # tracks how opponent adjusts vs us
        self.history = {}

    # -------------------------
    # UPDATE BEHAVIOR RESPONSE
    # -------------------------
    def update(self, opponent_name, our_action, opponent_action):

        if opponent_name not in self.history:
            self.history[opponent_name] = {
                "bluff_response": 0,
                "value_response": 0,
                "aggression_response": 0,
                "samples": 0
            }

        data = self.history[opponent_name]

        data["samples"] += 1

        # -------------------------
        # BLUFF RESPONSE TRACKING
        # -------------------------
        if our_action == "bluff":

            if opponent_action == "call":
                data["bluff_response"] += 1

        # -------------------------
        # VALUE RESPONSE TRACKING
        # -------------------------
        if our_action == "value":

            if opponent_action == "fold":
                data["value_response"] += 1

        # -------------------------
        # AGGRESSION RESPONSE TRACKING
        # -------------------------
        if opponent_action == "raise":
            data["aggression_response"] += 1

    # -------------------------
    # GET ADAPTATION PROFILE
    # -------------------------
    def get_profile(self, opponent_name):

        if opponent_name not in self.history:
            return {
                "bluff_penalty": 0.0,
                "value_bonus": 0.0,
                "aggression_shift": 0.0
            }

        data = self.history[opponent_name]
        s = max(1, data["samples"])

        bluff_rate = data["bluff_response"] / s
        value_rate = data["value_response"] / s
        aggression_rate = data["aggression_response"] / s

        profile = {
            "bluff_penalty": 0.0,
            "value_bonus": 0.0,
            "aggression_shift": 0.0
        }

        # -------------------------
        # OPPONENT ADAPTATION DETECTION
        # -------------------------

        # opponent calling bluffs too often → reduce bluffing
        if bluff_rate > 0.60:
            profile["bluff_penalty"] = 0.25

        # opponent folding too much → increase bluffing
        elif bluff_rate < 0.30:
            profile["bluff_penalty"] = -0.20

        # opponent folding vs value → increase value betting
        if value_rate > 0.55:
            profile["value_bonus"] = 0.20

        # opponent becoming aggressive → shift to trap strategy
        if aggression_rate > 0.40:
            profile["aggression_shift"] = 0.25

        return profile