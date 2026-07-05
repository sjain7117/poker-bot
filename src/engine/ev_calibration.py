class EVCalibrationEngine:

    def calculate_ev(self,
                     equity,
                     pot,
                     call_cost,
                     fold_equity=0.0,
                     position="BTN",
                     opponent_style="UNKNOWN",
                     is_bluff=False):

        win_prob = equity
        lose_prob = 1 - equity

        win_value = win_prob * pot
        loss_value = lose_prob * call_cost

        fold_value = fold_equity * pot if is_bluff else 0

        # -------------------------
        # POSITION (REDUCED IMPACT - avoid double counting)
        # -------------------------
        position_bonus = 0
        if position == "BTN":
            position_bonus = 0.25
        elif position == "CO":
            position_bonus = 0.15
        elif position == "SB":
            position_bonus = -0.15
        elif position == "BB":
            position_bonus = -0.2

        # -------------------------
        # OPPONENT EXPLOITATION (SOFTENED)
        # -------------------------
        opponent_bonus = 0

        if opponent_style == "TIGHT_PASSIVE":
            opponent_bonus = 0.25
        elif opponent_style == "LOOSE_PASSIVE":
            opponent_bonus = 0.15
        elif opponent_style == "LOOSE_AGGRESSIVE":
            opponent_bonus = -0.15
        elif opponent_style == "TIGHT_AGGRESSIVE":
            opponent_bonus = -0.1

        # -------------------------
        # BLUFF PENALTY (UNCHANGED BUT SAFE)
        # -------------------------
        bluff_penalty = 0
        if is_bluff:
            bluff_penalty = 0.25 * (1 - fold_equity)

        ev = (
            win_value
            - loss_value
            + fold_value
            + position_bonus
            + opponent_bonus
            - bluff_penalty
        )

        return ev

    def should_play(self, ev, threshold=0.0):
        return ev > threshold

    def classify_ev(self, ev):

        if ev > 4:
            return "VERY_STRONG"
        elif ev > 2:
            return "STRONG"
        elif ev > 0:
            return "SLIGHT_PLUS"
        elif ev > -2:
            return "SLIGHT_MINUS"
        else:
            return "BAD"