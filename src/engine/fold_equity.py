class FoldEquityEngine:
    def __init__(self):
        pass

    # -------------------------
    # MAIN FUNCTION
    # -------------------------
    def estimate(self, opponent, board, aggression_level="normal"):

        if not opponent:
            return 0.3  # unknown opponent = medium fold chance

        base_fold = 0.2

        # -------------------------
        # VPIP EFFECT (LOOSENESS)
        # -------------------------
        if opponent.vpip < 0.25:
            base_fold += 0.35  # tight player folds more

        elif opponent.vpip < 0.40:
            base_fold += 0.15

        else:
            base_fold -= 0.15  # loose players call more

        # -------------------------
        # PFR EFFECT (AGGRESSION)
        # -------------------------
        if opponent.pfr > 0.25:
            base_fold -= 0.10  # aggressive players don't fold easily

        elif opponent.pfr < 0.10:
            base_fold += 0.10  # passive players fold more

        # -------------------------
        # LEAK ADJUSTMENTS (VERY IMPORTANT)
        # -------------------------
        leaks = getattr(opponent, "leaks", [])

        if "OVERFOLDING" in leaks:
            base_fold += 0.25

        if "CALLING_STATION" in leaks:
            base_fold -= 0.30

        if "NIT" in leaks:
            base_fold += 0.20

        if "OVERAGGRESSIVE" in leaks:
            base_fold -= 0.15

        # -------------------------
        # BOARD TEXTURE EFFECT
        # -------------------------
        if len(board) >= 3:

            from treys import Card
            suits = [Card.int_to_str(c)[1] for c in board]
            ranks = [Card.int_to_str(c)[0] for c in board]

            # coordinated board → harder to fold
            if len(set(suits)) <= 2:
                base_fold -= 0.10

            # very connected board → more calls
            if len(set(ranks)) < len(ranks):
                base_fold -= 0.10

        # clamp
        return max(0.05, min(0.85, base_fold))