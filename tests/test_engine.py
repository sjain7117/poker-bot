"""Engine correctness tests. Run: python3 tests/test_engine.py"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.engine.poker_game_engine import PokerGameEngine, HERO, BOT

S, SB, BB = 200, 1, 2

def fresh(button=HERO, stacks=None):
    t = PokerGameEngine(S, SB, BB)
    if stacks: t.stacks = list(stacks)
    t.button = button; t.start_hand(); return t

def play(t, hero="call", bot="call"):
    def act(style):
        la = t.legal_actions(); a = la["actions"]
        if style == "shove":
            if la.get("raise"): return "raise", la["raise"]["max_to"]
            if la.get("bet"): return "bet", la["bet"]["max_to"]
        if "call" in a: return "call", None
        if "check" in a: return "check", None
        return "fold", None
    n = 0
    while not t.done and n < 60:
        n += 1
        k, amt = act(hero if t.to_act == HERO else bot)
        t.apply_action(k, amt)

def test_chip_conservation_checkdown():
    random.seed(0)
    for b in (HERO, BOT):
        t = fresh(b); play(t, "call", "call")
        assert sum(t.stacks) + t.pot == 2 * S, sum(t.stacks)

def test_chip_conservation_allin():
    random.seed(1)
    for b in (HERO, BOT):
        t = fresh(b); play(t, "shove", "call")
        assert sum(t.stacks) == 2 * S, sum(t.stacks)

def test_legal_actions():
    t = fresh(HERO)
    la = t.legal_actions()
    assert {"fold", "call", "raise"} <= set(la["actions"])
    assert la["raise"]["min_to"] > la["call_amount"]
    t.apply_action("call")
    la2 = t.legal_actions()
    assert la2["actions"] == ["check"]
    assert la2["bet"]["max_to"] > la2["bet"]["min_to"]

def test_open_bet_is_not_a_check():
    t = fresh(BOT); t.apply_action("call")
    assert t.legal_actions()["actions"] == ["check"]
    t.apply_action("bet", 58)
    assert t.street_commit[HERO] == 58
    assert t.street == "preflop"

def test_uncalled_excess_refunded():
    t = fresh(HERO, [200, 60]); play(t, "shove", "call")
    assert sum(t.stacks) == 260, sum(t.stacks)
    assert min(t.stacks) >= 0

def test_blinds_and_preflop_order():
    t = fresh(HERO)
    assert t.street_commit[HERO] == SB
    assert t.street_commit[BOT] == BB
    assert t.to_act == HERO

def test_postflop_order_bb_first():
    t = fresh(HERO); t.apply_action("call"); t.apply_action("check")
    assert t.street == "flop" and t.to_act == BOT

def test_pot_zeroed_showdown():
    random.seed(2)
    t = fresh(HERO); play(t, "shove", "call")
    assert t.done and t.pot == 0 and t.result["pot"] > 0

def test_pot_zeroed_fold():
    t = fresh(HERO)
    t.apply_action("raise", t.legal_actions()["raise"]["max_to"])
    t.apply_action("fold")
    assert t.done and t.result["reason"] == "fold"
    assert t.pot == 0 and sum(t.stacks) == 2 * S

if __name__ == "__main__":
    ts = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    p = 0
    for f in ts:
        try: f()
        except Exception as e: print("FAIL ", f.__name__, e)
        else: p += 1; print("ok   ", f.__name__)
    print("\n%d/%d passed" % (p, len(ts)))
    sys.exit(0 if p == len(ts) else 1)
