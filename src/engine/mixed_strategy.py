import random


class MixedStrategyEngine:

    def __init__(self):
        pass

    # -------------------------
    # MAIN MIXER
    # -------------------------
    def choose_line(self, base_line, equity, fold_prob, position, leaks):

        # -------------------------
        # BASE PROBABILITIES
        # -------------------------
        probs = {
            "value": 0.0,
            "bluff": 0.0,
            "trap": 0.0,
            "call": 0.0,
            "fold": 0.0
        }

        # -------------------------
        # VALUE HANDS
        # -------------------------
        if base_line == "value":
            probs["value"] = 0.70
            probs["call"] = 0.20
            probs["bluff"] = 0.05
            probs["fold"] = 0.05

        # -------------------------
        # BLUFF HANDS
        # -------------------------
        elif base_line == "bluff":
            probs["bluff"] = 0.55
            probs["fold"] = 0.25
            probs["call"] = 0.10
            probs["value"] = 0.10

        # -------------------------
        # TRAP HANDS
        # -------------------------
        elif base_line == "trap":
            probs["trap"] = 0.60
            probs["call"] = 0.25
            probs["value"] = 0.10
            probs["bluff"] = 0.05

        # -------------------------
        # CALL SPOTS
        # -------------------------
        else:
            probs["call"] = 0.60
            probs["fold"] = 0.30
            probs["value"] = 0.05
            probs["bluff"] = 0.05

        # -------------------------
        # POSITION ADJUSTMENTS
        # -------------------------
        if position == "BTN":
            probs["bluff"] += 0.10

        if position == "UTG":
            probs["value"] += 0.10
            probs["bluff"] -= 0.10

        # -------------------------
        # LEAK ADJUSTMENTS
        # -------------------------
        if "OVERFOLDING" in leaks:
            probs["bluff"] += 0.10

        if "CALLING_STATION" in leaks:
            probs["bluff"] -= 0.15
            probs["value"] += 0.10

        if "OVERAGGRESSIVE" in leaks:
            probs["trap"] += 0.15

        # -------------------------
        # NORMALIZE
        # -------------------------
        total = sum(probs.values())
        for k in probs:
            probs[k] /= total

        # -------------------------
        # SAMPLE ACTION
        # -------------------------
        r = random.random()
        cumulative = 0

        for action, p in probs.items():
            cumulative += p
            if r <= cumulative:
                return action

        return base_line