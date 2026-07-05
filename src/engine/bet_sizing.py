class BetSizingEngine:

    def __init__(self):

        self.small_bet = 0.33
        self.medium_bet = 0.60
        self.large_bet = 0.90

    def get_bet_size(self, equity, pot, hand_strength, fold_prob, is_bluff=False):

        if equity < 0.25 and not is_bluff:
            return 0

        if not is_bluff:

            if equity > 0.70:
                return pot * self.large_bet

            if equity > 0.50:
                return pot * self.medium_bet

            return pot * self.small_bet

        else:

            if fold_prob > 0.60:
                return pot * self.medium_bet

            if fold_prob > 0.45:
                return pot * self.small_bet

            return pot * 0.25

    def should_commit(self, equity, pot, call_cost):

        pot_odds = call_cost / (pot + call_cost)

        return equity >= pot_odds * 0.85