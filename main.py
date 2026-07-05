"""
main.py — Evaluation harness.

Plays the RuleBot heads-up against a set of baseline opponents and reports its
win-rate in bb/100 (big blinds won per 100 hands), the standard poker yardstick.
Run from the project root:  python main.py
"""
import random
from src.engine.poker_game_engine import PokerGameEngine, HERO, BOT
from src.bots.rule_bot import RuleBot

STARTING_STACK, SB, BB = 200, 1, 2


# ---- baseline opponents (the "hero" seat) -------------------------------- #
def calling_station(t):
    a = t.legal_actions()["actions"]
    if "check" in a:
        return "check", None
    if "call" in a:
        return "call", None
    return "check", None


def nit(t):
    a = t.legal_actions()["actions"]
    return ("check", None) if "check" in a else ("fold", None)


def maniac(t):
    la = t.legal_actions(); a = la["actions"]
    if "raise" in a and random.random() < 0.6:
        spec = la["raise"]
        return "raise", min(spec["max_to"], spec["min_to"] + 4)
    if "bet" in a and random.random() < 0.6:
        spec = la["bet"]
        return "bet", min(spec["max_to"], spec["min_to"] + 4)
    if "call" in a:
        return "call", None
    return ("check", None) if "check" in a else ("fold", None)


def semi_aggressive(t):
    la = t.legal_actions(); a = la["actions"]
    if "check" in a:
        return ("bet", la["bet"]["min_to"]) if random.random() < 0.3 else ("check", None)
    if random.random() < 0.5 and "call" in a:
        return "call", None
    return ("fold", None) if "fold" in a else ("check", None)


def run_bot(t, bot):
    g = 0
    while (not t.done and t.to_act == BOT
           and t.street not in ("showdown", "done") and g < 30):
        g += 1
        d = bot.decide(t.view_for(BOT, "hero"))
        t.apply_action(d["action"], d.get("amount"))


def evaluate(opponent, hands=1000, seed=1, sims=None):
    random.seed(seed)
    bot = RuleBot("RuleBot", seed=seed)
    if sims:
        bot.equity_engine.simulations = sims
    net = 0
    for h in range(hands):
        t = PokerGameEngine(STARTING_STACK, SB, BB)
        t.button = HERO if h % 2 == 0 else BOT
        before = t.stacks[BOT]
        t.start_hand(); bot.new_hand("hero")
        guard = 0
        while not t.done and guard < 60:
            guard += 1
            if t.to_act == BOT:
                run_bot(t, bot)
            else:
                kind, amt = opponent(t)
                bot.observe_opponent_action("hero", kind, t.street)
                t.apply_action(kind, amt)
        gain = t.stacks[BOT] - before
        net += gain
        bot.settle_hand(gain)
    return (net / BB) / hands * 100


if __name__ == "__main__":
    print("RuleBot evaluation — win-rate in bb/100 (higher is better)\n")
    for name, fn, n in [
        ("Nit (folds to pressure)", nit, 800),
        ("Semi-aggressive", semi_aggressive, 800),
        ("Maniac (over-aggressive)", maniac, 800),
        ("Calling station", calling_station, 1200),
    ]:
        bb100 = evaluate(fn, hands=n, sims=140)
        print(f"  vs {name:<26} {bb100:+7.1f} bb/100   ({n} hands)")
    print("\n(Positive = RuleBot profits. Realistic opponents fold sometimes,")
    print(" so the bot's value+bluff mixing earns more against them than")
    print(" against a pure never-fold station, which is high-variance.)")