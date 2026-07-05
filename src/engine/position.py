class PositionEngine:
    """
    Handles poker position-based strategy adjustments
    """

    def __init__(self):

        # standard 6-max mapping
        self.positions = [
            "UTG",
            "MP",
            "CO",
            "BTN",
            "SB",
            "BB"
        ]

    # -------------------------
    # GET POSITION INDEX
    # -------------------------
    def get_position(self, player_index, dealer_index, num_players=6):

        # rotate table based on dealer
        relative_index = (player_index - dealer_index) % num_players

        return self.positions[relative_index]

    # -------------------------
    # POSITION STRENGTH MULTIPLIER
    # -------------------------
    def position_multiplier(self, position):

        # early position = tight
        if position == "UTG":
            return 0.90

        if position == "MP":
            return 0.95

        # late position = aggressive
        if position == "CO":
            return 1.05

        if position == "BTN":
            return 1.10

        # blinds = defensive + variance
        if position == "SB":
            return 0.98

        if position == "BB":
            return 1.00

        return 1.0

    # -------------------------
    # STRATEGY SHIFT (VERY IMPORTANT)
    # -------------------------
    def strategy_modifier(self, position):

        if position == "UTG":
            return {
                "bluff_bias": -0.10,
                "value_bias": 0.10
            }

        if position == "MP":
            return {
                "bluff_bias": -0.05,
                "value_bias": 0.05
            }

        if position == "CO":
            return {
                "bluff_bias": 0.05,
                "value_bias": 0.00
            }

        if position == "BTN":
            return {
                "bluff_bias": 0.15,
                "value_bias": -0.05
            }

        if position == "SB":
            return {
                "bluff_bias": 0.05,
                "value_bias": 0.05
            }

        if position == "BB":
            return {
                "bluff_bias": -0.02,
                "value_bias": 0.02
            }

        return {
            "bluff_bias": 0.0,
            "value_bias": 0.0
        }