class BluffControlEngine:

    def __init__(self):

        self.bluffs_used = 0
        self.hands_played = 0

        self.max_bluff_rate = 0.08
        self.last_bluff_hand = -100
        self.cooldown = 3

        self.net_result = 0

    def update_hand(self):
        self.hands_played += 1

    def can_bluff(self, current_hand):

        if current_hand - self.last_bluff_hand < self.cooldown:
            return False

        if self.hands_played > 0:
            if self.bluffs_used / self.hands_played > self.max_bluff_rate:
                return False

        if self.net_result < -10:
            return False

        return True

    def register_bluff(self, current_hand):
        self.bluffs_used += 1
        self.last_bluff_hand = current_hand