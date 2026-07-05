class OpponentModel:
    def __init__(self, name):
        self.name = name

        # -------------------------
        # TRACKING
        # -------------------------
        self.hands_played = 0

        self.preflop_raises = 0
        self.preflop_calls = 0

        self.postflop_raises = 0
        self.postflop_calls = 0
        self.checks = 0

        self.folds = 0

        # -------------------------
        # METRICS
        # -------------------------
        self.vpip = 0.0
        self.pfr = 0.0
        self.af = 0.0

        self.style = "UNKNOWN"

        # -------------------------
        # LEAK TAGS (FOR YOUR BOT)
        # -------------------------
        self.leaks = []
        self._vpip_counted = False

        # richer in-session signals for real opponent adaptation
        self.aggressive_actions = 0     # bets + raises
        self.passive_actions = 0        # calls + checks
        self.total_folds = 0
        self.total_decisions = 0

    # -------------------------
    # UPDATE ACTIONS
    # -------------------------
    def new_hand(self):
        # call once at the start of each hand so VPIP/PFR denominators are
        # per-hand, not per-action
        self.hands_played += 1
        self._vpip_counted = False

    def update(self, action, street="preflop"):
        self.total_decisions += 1
        if action in ("bet", "raise"):
            self.aggressive_actions += 1
        elif action in ("call", "check"):
            self.passive_actions += 1
        elif action == "fold":
            self.total_folds += 1

        if street == "preflop":
            if action in ("raise", "bet"):
                self.preflop_raises += 1
            elif action == "call":
                self.preflop_calls += 1

        else:
            if action in ("raise", "bet"):
                self.postflop_raises += 1
            elif action == "call":
                self.postflop_calls += 1
            elif action == "check":
                self.checks += 1
            elif action == "fold":
                self.folds += 1

        self.compute_stats()

    # -------------------------
    # COMPUTE METRICS
    # -------------------------
    def compute_stats(self):

        if self.hands_played == 0:
            return

        preflop_total = self.preflop_raises + self.preflop_calls

        # VPIP = voluntarily entered pot
        self.vpip = preflop_total / self.hands_played

        # PFR = preflop raise frequency
        self.pfr = self.preflop_raises / self.hands_played

        # Aggression Factor (postflop)
        passive = self.postflop_calls + self.checks + 1e-6
        aggressive = self.postflop_raises + 1e-6

        self.af = aggressive / passive

        self.classify()
        self.detect_leaks()

    # -------------------------
    # CLASSIFICATION SYSTEM
    # -------------------------
    def classify(self):

        vpip = self.vpip
        pfr = self.pfr

        if vpip < 0.25 and pfr >= 0.18:
            self.style = "TIGHT_AGGRESSIVE"

        elif vpip >= 0.30 and pfr >= 0.25:
            self.style = "LOOSE_AGGRESSIVE"

        elif vpip < 0.25 and pfr <= 0.10:
            self.style = "TIGHT_PASSIVE"

        elif vpip >= 0.40 and pfr <= 0.15:
            self.style = "LOOSE_PASSIVE"

        else:
            self.style = "MIXED"

    # -------------------------
    # LEAK DETECTION (IMPORTANT FOR RULEBOT)
    # -------------------------
    def detect_leaks(self):

        self.leaks = []

        # OVERFOLDING
        if self.vpip < 0.25 and self.af < 0.8:
            self.leaks.append("OVERFOLDING")

        # CALLING STATION
        if self.vpip > 0.55 and self.pfr < 0.15:
            self.leaks.append("CALLING_STATION")

        # NIT
        if self.vpip < 0.20:
            self.leaks.append("NIT")

        # OVER AGGRESSIVE
        if self.pfr > 0.30 and self.af > 1.8:
            self.leaks.append("OVERAGGRESSIVE")

    # -------------------------
    # SESSION PROFILE (drives real adaptation)
    # -------------------------
    def profile(self):
        acts = self.aggressive_actions + self.passive_actions + self.total_folds
        aggression = self.aggressive_actions / acts if acts else 0.3
        fold_tendency = self.total_folds / acts if acts else 0.3
        # confidence ramps up over the first ~20 observed actions
        confidence = min(1.0, acts / 20.0)
        maniac = aggression > 0.5 and self.vpip > 0.5
        return {
            "aggression": aggression,
            "fold_tendency": fold_tendency,
            "confidence": confidence,
            "maniac": maniac,
            "samples": acts,
        }

    # -------------------------
    # RANGE GENERATION (CRITICAL FOR MONTE CARLO)
    # -------------------------
    def get_range(self):

        if self.style == "TIGHT_PASSIVE":
            return {
                "distribution": {"strong": 0.60, "medium": 0.25, "weak": 0.15}
            }

        if self.style == "LOOSE_PASSIVE":
            return {
                "distribution": {"strong": 0.30, "medium": 0.40, "weak": 0.30}
            }

        if self.style == "LOOSE_AGGRESSIVE":
            return {
                "distribution": {"strong": 0.30, "medium": 0.35, "weak": 0.35}
            }

        if self.style == "TIGHT_AGGRESSIVE":
            return {
                "distribution": {"strong": 0.55, "medium": 0.30, "weak": 0.15}
            }

        return {
            "distribution": {"strong": 0.40, "medium": 0.35, "weak": 0.25}
        }

    # -------------------------
    # HELPERS
    # -------------------------
    def is_bluff_target(self):
        return "OVERFOLDING" in self.leaks

    def is_value_target(self):
        return self.style in ["LOOSE_PASSIVE", "CALLING_STATION"]

    def is_trap_opponent(self):
        return self.style in ["LOOSE_AGGRESSIVE", "OVERAGGRESSIVE"]