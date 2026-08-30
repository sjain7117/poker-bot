"""
tools/benchmark.py — Regression harness for RuleBot.

Plays the bot heads-up against scripted baselines and reports net chips per 100
hands with a standard error, so a change to the bot can be told apart from
noise. Not run in CI. Run from the project root:

    python3 tools/benchmark.py --hands 2000

The baselines are deliberately trivial. They exist to catch regressions, not to
say anything about how the bot fares against a real player.

treys seeds each Deck from OS entropy and three of the decision modules draw
from the global random stream, so a run pins both: the deck factory is replaced
with a seeded one and random.seed is set per opponent. Same --seed therefore
reproduces a run exactly. It does not buy much as a variance-reduction trick:
across two configurations the per-hand results correlate at r=0.04, because how
a hand plays out is dominated by the actions taken, not the cards dealt.
"""
import argparse
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from treys import Deck

from src.bots.rule_bot import RuleBot
from src.engine import poker_game_engine as pge
from src.engine.poker_game_engine import PokerGameEngine, HERO, BOT

STARTING_STACK, SB, BB = 200, 1, 2
ACTION_GUARD = 60


# ---- scripted baselines (the "hero" seat) -------------------------------- #
def always_call(t, rng):
    a = t.legal_actions()["actions"]
    if "call" in a:
        return "call", None
    return ("check", None) if "check" in a else ("fold", None)


def fold_unless_free(t, rng):
    a = t.legal_actions()["actions"]
    return ("check", None) if "check" in a else ("fold", None)


def loose_aggressive(t, rng):
    la = t.legal_actions(); a = la["actions"]
    if "raise" in a and rng.random() < 0.55:
        spec = la["raise"]
        return "raise", min(spec["max_to"], spec["min_to"] + 4)
    if "bet" in a and rng.random() < 0.55:
        spec = la["bet"]
        return "bet", min(spec["max_to"], spec["min_to"] + 4)
    if "call" in a:
        return "call", None
    return ("check", None) if "check" in a else ("fold", None)


OPPONENTS = {
    "always-call": always_call,
    "fold-unless-free": fold_unless_free,
    "loose-aggressive": loose_aggressive,
}


# ---- harness ------------------------------------------------------------- #
class SeededDecks:
    """Stands in for treys.Deck so a run's cards follow from its seed."""

    def __init__(self, seed):
        self.rng = random.Random(seed)

    def __call__(self):
        return Deck(seed=self.rng.getrandbits(63))


def run_bot(t, bot):
    g = 0
    while (not t.done and t.to_act == BOT
           and t.street not in ("showdown", "done") and g < 30):
        g += 1
        d = bot.decide(t.view_for(BOT, "hero"))
        t.apply_action(d["action"], d.get("amount"))


def play(opponent, hands, seed, sims):
    """Per-hand net chips for the bot. Fresh stacks each hand, so samples are
    independent and the button alternates."""
    # line_labeler, mixed_strategy and frequency_prior draw from the global
    # stream, so it has to be seeded too or runs do not reproduce.
    random.seed(seed)
    pge.Deck = SeededDecks(seed)
    rng = random.Random(seed)
    bot = RuleBot("RuleBot", seed=seed)
    if sims:
        bot.equity_engine.simulations = sims
    nets = []
    for h in range(hands):
        t = PokerGameEngine(STARTING_STACK, SB, BB)
        t.button = HERO if h % 2 == 0 else BOT
        t.start_hand()
        bot.new_hand("hero")
        guard = 0
        while not t.done and guard < ACTION_GUARD:
            guard += 1
            if t.to_act == BOT:
                run_bot(t, bot)
            else:
                kind, amt = opponent(t, rng)
                bot.observe_opponent_action("hero", kind, t.street)
                t.apply_action(kind, amt)
        gain = t.stacks[BOT] - STARTING_STACK
        nets.append(gain)
        bot.settle_hand(gain)
    return nets


def summarise(nets):
    n = len(nets)
    mean = statistics.fmean(nets)
    sd = statistics.stdev(nets) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    return {
        "hands": n,
        "per100": mean * 100,
        "se100": se * 100,
        "sd": sd,
    }


def hands_for(sd, delta):
    """Hands per configuration to resolve a delta chips/100 difference between
    two independent runs at 95% confidence."""
    if delta <= 0 or sd <= 0:
        return float("inf")
    return 2 * (1.96 * 100 * sd / delta) ** 2


def min_detectable(sd, n):
    """Smallest chips/100 difference this many hands can resolve."""
    if n <= 0:
        return float("inf")
    return 1.96 * 100 * sd * math.sqrt(2.0 / n)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hands", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sims", type=int, default=140)
    ap.add_argument("--opponent", choices=sorted(OPPONENTS), default=None)
    args = ap.parse_args()

    names = [args.opponent] if args.opponent else sorted(OPPONENTS)
    try:
        rows = []
        for name in names:
            r = summarise(play(OPPONENTS[name], args.hands, args.seed, args.sims))
            r["name"] = name
            rows.append(r)
    finally:
        pge.Deck = Deck

    print("RuleBot vs scripted baselines — seed %d, %d sims/decision\n"
          % (args.seed, args.sims))
    print("%-18s %7s %12s %10s %22s" %
          ("opponent", "hands", "chips/100", "± SE", "95% CI"))
    print("-" * 74)
    for r in rows:
        lo = r["per100"] - 1.96 * r["se100"]
        hi = r["per100"] + 1.96 * r["se100"]
        print("%-18s %7d %12.1f %10.1f %10.1f .. %-10.1f"
              % (r["name"], r["hands"], r["per100"], r["se100"], lo, hi))

    print("\nWhat this many hands can actually resolve (95% confidence):")
    print("%-18s %14s %10s %12s %12s"
          % ("opponent", "min effect", "as % base", "n for 5%", "n for 10%"))
    print("-" * 72)
    for r in rows:
        mde = min_detectable(r["sd"], r["hands"])
        base = abs(r["per100"]) or 1.0
        print("%-18s %14.1f %9.1f%% %12.0f %12.0f"
              % (r["name"], mde, 100 * mde / base,
                 hands_for(r["sd"], base * 0.05),
                 hands_for(r["sd"], base * 0.10)))
    print("\nA change smaller than the min effect column cannot be told from")
    print("noise at this N, whatever the point estimates say.")


if __name__ == "__main__":
    main()
