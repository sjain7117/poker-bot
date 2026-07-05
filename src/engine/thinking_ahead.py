import random


class ThinkingAheadEngine:
    def __init__(self):
        pass

    # -------------------------
    # MAIN FUNCTION
    # -------------------------
    def evaluate_line(self, equity, hand_strength, fold_prob,
                      opponent_style, pot, aggression_type):

        # -------------------------
        # BASE EV ESTIMATION
        # -------------------------
        base_ev = equity * pot

        # -------------------------
        # FUTURE STREET SIMULATION (SIMPLIFIED MODEL)
        # -------------------------
        turn_factor = 0.85
        river_factor = 0.75

        # opponent continuation probability
        continue_prob = 1 - fold_prob

        # expected future value if called
        future_ev = (
            base_ev * turn_factor * river_factor
        )

        # bluff line EV
        bluff_ev = (fold_prob * pot) - (continue_prob * (1 - equity) * pot)

        # value line EV
        value_ev = equity * pot * 1.2

        # trap line EV (slow play strong hands)
        trap_ev = (hand_strength * pot * 1.3) * continue_prob

        # -------------------------
        # LINE SELECTION
        # -------------------------
        lines = {
            "bluff": bluff_ev,
            "value": value_ev,
            "trap": trap_ev
        }

        best_line = max(lines, key=lines.get)

        return {
            "best_line": best_line,
            "ev": lines[best_line],
            "all_lines": lines
        }

    # -------------------------
    # MULTI-STREET FORECAST (SIMPLIFIED TREE)
    # -------------------------
    def forecast(self, equity, hand_strength, fold_prob):

        scenarios = []

        # flop → turn → river simulation branches
        for i in range(5):

            noise = random.uniform(-0.05, 0.05)

            scenario_ev = (
                equity * 0.5 +
                hand_strength * 0.3 +
                fold_prob * 0.2 +
                noise
            )

            scenarios.append(scenario_ev)

        return {
            "avg_ev": sum(scenarios) / len(scenarios),
            "variance": max(scenarios) - min(scenarios)
        }