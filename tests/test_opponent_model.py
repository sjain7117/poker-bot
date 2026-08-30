"""Opponent-model correctness tests. Run: python3 tests/test_opponent_model.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.engine.opponent_model import OpponentModel, MIN_AF_ACTIONS

PRE_RAISE = ("raise", "preflop")
PRE_CALL = ("call", "preflop")
PRE_FOLD = ("fold", "preflop")

def played(hands):
    m = OpponentModel("hero")
    for actions in hands:
        m.new_hand()
        for action, street in actions:
            m.update(action, street)
    return m

def test_vpip_pfr_never_exceed_one():
    m = played([[PRE_RAISE] * 3] * 10)
    assert m.vpip == 1.0, m.vpip
    assert m.pfr == 1.0, m.pfr
    assert m.preflop_raises == 10, m.preflop_raises

def test_repeated_preflop_calls_count_once():
    m = played([[PRE_CALL] * 3] * 10)
    assert m.vpip == 1.0, m.vpip
    assert m.pfr == 0.0, m.pfr
    assert m.preflop_calls == 10, m.preflop_calls

def test_call_then_raise_counts_once_each():
    m = played([[PRE_CALL, PRE_RAISE]])
    assert m.vpip == 1.0, m.vpip
    assert m.pfr == 1.0, m.pfr
    assert m.preflop_calls == 1, m.preflop_calls
    assert m.preflop_raises == 1, m.preflop_raises

def test_folded_hands_are_zero():
    m = played([[PRE_FOLD]] * 10)
    assert m.hands_played == 10, m.hands_played
    assert m.vpip == 0.0, m.vpip
    assert m.pfr == 0.0, m.pfr

def test_partial_entry_is_a_fraction():
    m = played([[PRE_CALL]] * 2 + [[PRE_FOLD]] * 8)
    assert m.vpip == 0.2, m.vpip
    assert m.pfr == 0.0, m.pfr

def test_af_leaks_gated_below_threshold():
    short = [("check", "flop")] * (MIN_AF_ACTIONS - 1)
    m = played([[PRE_FOLD]] * 9 + [short])
    assert m.postflop_actions == MIN_AF_ACTIONS - 1, m.postflop_actions
    assert m.vpip < 0.25 and m.af < 0.8, (m.vpip, m.af)
    assert "OVERFOLDING" not in m.leaks, m.leaks

def test_af_leaks_reachable_above_threshold():
    enough = [("check", "flop")] * MIN_AF_ACTIONS
    m = played([[PRE_FOLD]] * 9 + [enough])
    assert m.postflop_actions == MIN_AF_ACTIONS, m.postflop_actions
    assert "OVERFOLDING" in m.leaks, m.leaks

def test_overaggressive_needs_postflop_sample():
    short = [PRE_RAISE] + [("bet", "flop")] * (MIN_AF_ACTIONS - 1)
    enough = [PRE_RAISE] + [("bet", "flop")] * MIN_AF_ACTIONS
    gated = played([[PRE_RAISE]] * 9 + [short])
    assert "OVERAGGRESSIVE" not in gated.leaks, gated.leaks
    m = played([[PRE_RAISE]] * 9 + [enough])
    assert m.pfr > 0.30 and m.af > 1.8, (m.pfr, m.af)
    assert "OVERAGGRESSIVE" in m.leaks, m.leaks

def test_no_af_leak_without_postflop_play():
    m = played([[PRE_FOLD]] * 10)
    assert m.af == 1.0, m.af
    assert "OVERFOLDING" not in m.leaks, m.leaks

def test_profile_counters_stay_per_action():
    hand = [PRE_RAISE, ("call", "flop"), ("check", "turn"), ("bet", "river")]
    m = played([hand] * 2)
    p = m.profile()
    assert m.total_decisions == 8, m.total_decisions
    assert m.aggressive_actions == 4, m.aggressive_actions
    assert m.passive_actions == 4, m.passive_actions
    assert p["aggression"] == 0.5, p["aggression"]
    assert p["fold_tendency"] == 0.0, p["fold_tendency"]
    assert p["confidence"] == 0.4, p["confidence"]

if __name__ == "__main__":
    ts = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    p = 0
    for f in ts:
        try: f()
        except Exception as e: print("FAIL ", f.__name__, e)
        else: p += 1; print("ok   ", f.__name__)
    print("\n%d/%d passed" % (p, len(ts)))
    sys.exit(0 if p == len(ts) else 1)
