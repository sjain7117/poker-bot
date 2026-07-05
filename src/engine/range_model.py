"""
range_model.py — Range-Based Opponent Modelling.
"""
import random
from treys import Card

RANK_ORDER = "23456789TJQKA"
_VAL = {r: i + 2 for i, r in enumerate(RANK_ORDER)}
_CHEN_HIGH = {14: 10, 13: 8, 12: 7, 11: 6}


# --------------------------------------------------------------------------- #
#  Canonical hand codes + Chen preflop scoring
# --------------------------------------------------------------------------- #
def hand_code(two_cards):
    """'AKs' / 'AKo' / 'TT' from two treys ints."""
    r1, s1 = Card.int_to_str(two_cards[0])
    r2, s2 = Card.int_to_str(two_cards[1])
    hi, lo = sorted([r1, r2], key=lambda r: _VAL[r], reverse=True)
    if r1 == r2:
        return hi + lo
    return hi + lo + ("s" if s1 == s2 else "o")


def chen_from_code(code):
    r1, r2 = code[0], code[1]
    suited = code.endswith("s")
    v1, v2 = _VAL[r1], _VAL[r2]
    hi = max(v1, v2)
    base = _CHEN_HIGH.get(hi, hi / 2.0)
    if r1 == r2:                        # pair
        return max(base * 2, 5)
    score = base + (2 if suited else 0)
    gap = abs(v1 - v2) - 1
    score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if gap <= 1 and hi < 12:
        score += 1
    return score


def chen_score(two_cards):
    return chen_from_code(hand_code(two_cards))


def _all_codes():
    codes = set()
    for a in RANK_ORDER:
        for b in RANK_ORDER:
            if _VAL[a] < _VAL[b]:
                continue
            codes.add(a + b if a == b else a + b + "s")
            if a != b:
                codes.add(a + b + "o")
    return codes


_CODE_SCORES = {c: chen_from_code(c) for c in _all_codes()}
_SORTED = sorted(_CODE_SCORES.values())


def preflop_percentile(two_cards):
    s = chen_score(two_cards)
    return sum(1 for v in _SORTED if v <= s) / len(_SORTED)


def range_weight_fn(top_frac):
    """Weight function for the equity engine: hands in the top `top_frac` by
    Chen score get weight 1.0, with a soft taper just below the cutoff."""
    top_frac = max(0.02, min(1.0, top_frac))
    if top_frac >= 0.999:
        return lambda code: 1.0
    cutoff = _SORTED[int((1 - top_frac) * (len(_SORTED) - 1))]
    band = 1.5

    def weight(code):
        s = _CODE_SCORES.get(code) or chen_from_code(code)
        if s >= cutoff:
            return 1.0
        if s >= cutoff - band:
            return (s - (cutoff - band)) / band
        return 0.0
    return weight


# --------------------------------------------------------------------------- #
#  Original style-bucket range model (bug fixed)
# --------------------------------------------------------------------------- #
class RangeModel:
    def __init__(self):
        self.base_ranges = {
            "TIGHT_PASSIVE":    {"strong": 0.60, "medium": 0.25, "weak": 0.15},
            "LOOSE_PASSIVE":    {"strong": 0.35, "medium": 0.40, "weak": 0.25},
            "LOOSE_AGGRESSIVE": {"strong": 0.30, "medium": 0.35, "weak": 0.35},
            "TIGHT_AGGRESSIVE": {"strong": 0.55, "medium": 0.30, "weak": 0.15},
            "UNKNOWN":          {"strong": 0.40, "medium": 0.35, "weak": 0.25},
            "MIXED":            {"strong": 0.40, "medium": 0.35, "weak": 0.25},
        }

    def get_range(self, opponent_style, board):
        base = self.base_ranges.get(opponent_style, self.base_ranges["UNKNOWN"])
        strong, medium, weak = base["strong"], base["medium"], base["weak"]
        if len(board) >= 3:
            # board is treys ints — decode properly
            suits = [Card.int_to_str(c)[1] for c in board]
            ranks = [Card.int_to_str(c)[0] for c in board]
            if len(set(suits)) <= 2:
                strong += 0.05; weak -= 0.05
            if len(set(ranks)) < len(ranks):
                strong += 0.07; weak -= 0.07
        total = strong + medium + weak
        return {"strong": strong / total, "medium": medium / total,
                "weak": weak / total}

    def estimate_opponent_strength(self, opponent_style, board):
        r = self.get_range(opponent_style, board)
        return 1.0 * r["strong"] + 0.5 * r["medium"] + 0.1 * r["weak"]

    # style -> approximate fraction of hands the opponent still holds,
    # used to drive range-weighted equity.
    def style_to_frac(self, opponent_style, aggression_level=0, leaks=None):
        # This is the fraction of hands the opponent CONTINUES with — i.e.
        # their calling range. Loose/passive players call down with almost
        # anything, so equity should be measured against a wide range (which
        # means our real equity is higher and we value-bet bigger). Tight
        # players continue with much less.
        base = {
            "TIGHT_PASSIVE": 0.34, "TIGHT_AGGRESSIVE": 0.28,
            "LOOSE_PASSIVE": 0.55, "LOOSE_AGGRESSIVE": 0.55,
            "MIXED": 0.48, "UNKNOWN": 0.50,
        }.get(opponent_style, 0.50)
        leaks = leaks or []
        if "CALLING_STATION" in leaks:
            base = max(base, 0.68)   # calls wide, but still be selective
        if "NIT" in leaks:
            base = min(base, 0.24)
        if "OVERFOLDING" in leaks:
            base = min(base, 0.35)
        # A bet/raise from the opponent narrows their continue range.
        tighten = {0: 1.0, 1: 0.7, 2: 0.45}.get(aggression_level, 1.0)
        return max(0.08, min(1.0, base * tighten))

    def villain_bet_frac(self, aggression, level, confidence, leaks=None):
        """Width of the range the villain is BETTING/RAISING with.

        This is the crux of playing the player: a habitual aggressor bets a
        wide range (lots of air), so facing their bet we should NOT tighten
        their range and fold — we keep it wide and continue/punish. A passive
        player who suddenly bets has a narrow, strong range, so we respect it.
          aggression : 0..1 measured frequency of aggressive actions
          level      : 0 (small) .. 2 (pot+/overbet) sizing of the bet faced
          confidence : 0..1 how much data we have on them
        """
        leaks = leaks or []
        # measured betting-range width from their aggression
        raw = 0.12 + aggression * 0.85          # maniac ~0.9, nit ~0.20
        raw *= (1.0 - 0.12 * level)             # bigger bets slightly narrower
        if "OVERAGGRESSIVE" in leaks:
            raw = max(raw, 0.70)
        if "NIT" in leaks:
            raw = min(raw, 0.30)
        # before we know them, assume a fairly wide default (don't over-fold)
        default = 0.45
        frac = confidence * raw + (1.0 - confidence) * default
        return max(0.08, min(0.95, frac))