"""Session-layer tests for api/server.py. Run: python3 tests/test_sessions.py

Needs httpx (fastapi.testclient): python3 -m pip install -r requirements-dev.txt
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Eviction limits are read from the environment when api.server is imported,
# so they have to be set before the import below, not inside a test.
os.environ["MAX_SESSIONS"] = "3"
os.environ["SESSION_TTL_SECONDS"] = "1"

from fastapi.testclient import TestClient
from api import server

ENV_MAX = server.MAX_SESSIONS        # 3, parsed from the env at import
ENV_TTL = server.SESSION_TTL         # 1, parsed from the env at import

# A one-second TTL is what test_session_expires_after_ttl needs; every other
# test would race the sweep under it, so they run with expiry out of the way.
IDLE_TTL = 10_000
server.SESSION_TTL = IDLE_TTL

client = TestClient(server.app)


def start(sid, stack=200, buyin=100.0):
    r = client.post("/start", json={"stack": stack, "buyin": buyin},
                    headers={"X-Session-Id": sid})
    assert r.status_code == 200, r.text
    return r.json()

def state(sid):
    return client.get("/state", headers={"X-Session-Id": sid})

def act(sid, kind, amount=None):
    return client.post("/action", json={"kind": kind, "amount": amount},
                       headers={"X-Session-Id": sid})

def hero_move(s):
    """A cheap legal action for the hero in state s, or None if not their turn."""
    acts = (s.get("legal") or {}).get("actions", [])
    for k in ("check", "call", "fold"):
        if k in acts: return k
    return None

def snapshot(s):
    return {k: s[k] for k in ("board", "street", "stacks", "ledger")}


def test_sessions_are_independent():
    a = start("sess-a", stack=200, buyin=100.0)
    b = start("sess-b", stack=400, buyin=50.0)
    assert a["stakes"]["stack"] == 200 and a["stakes"]["buyin"] == 100.0, a["stakes"]
    assert b["stakes"]["stack"] == 400 and b["stakes"]["buyin"] == 50.0, b["stakes"]

    b_before = snapshot(state("sess-b").json())
    a_before = snapshot(a)
    moved = False
    for _ in range(4):
        k = hero_move(state("sess-a").json())
        if k is None: break
        assert act("sess-a", k).status_code == 200
        moved = True
    assert moved, "hero never got a turn in sess-a"
    assert snapshot(state("sess-a").json()) != a_before, "action was a no-op"

    assert snapshot(state("sess-b").json()) == b_before, "sess-a leaked into sess-b"

def test_unknown_session_is_409():
    for r in (state("no-such-session"), act("no-such-session", "check")):
        assert r.status_code == 409, r.status_code
        assert r.json()["expired"] is True, r.json()

def test_missing_session_header_is_409():
    r = client.get("/state")
    assert r.status_code == 409, r.status_code
    assert r.json()["expired"] is True, r.json()
    r = client.post("/action", json={"kind": "check", "amount": None})
    assert r.status_code == 409, r.status_code

def test_start_echoes_session_id():
    assert start("echo-me")["session_id"] == "echo-me"
    # No header: the server mints one and it addresses a real session.
    r = client.post("/start", json={"stack": 200, "buyin": 100.0})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert sid and state(sid).status_code == 200

def test_health_is_ok_and_creates_no_session():
    server._sessions.clear()
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert r.json()["sessions"] == 0, r.json()
    assert len(server._sessions) == 0, len(server._sessions)

def test_max_sessions_is_a_hard_cap():
    assert ENV_MAX == 3, ENV_MAX
    server._sessions.clear()
    ids = ["cap-%d" % i for i in range(5)]
    for sid in ids:
        start(sid)
    assert len(server._sessions) == ENV_MAX, len(server._sessions)
    assert state(ids[0]).status_code == 409, "oldest session survived the cap"
    assert state(ids[1]).status_code == 409, "oldest session survived the cap"
    assert state(ids[4]).status_code == 200, "newest session was evicted"

def test_session_expires_after_ttl():
    assert ENV_TTL == 1, ENV_TTL
    server._sessions.clear()
    server.SESSION_TTL = ENV_TTL
    try:
        start("ttl-me")
        assert state("ttl-me").status_code == 200
        time.sleep(ENV_TTL + 0.3)
        r = state("ttl-me")
        assert r.status_code == 409, r.status_code
        assert r.json()["expired"] is True, r.json()
    finally:
        server.SESSION_TTL = IDLE_TTL


if __name__ == "__main__":
    ts = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    p = 0
    for f in ts:
        try: f()
        except Exception as e: print("FAIL ", f.__name__, e)
        else: p += 1; print("ok   ", f.__name__)
    print("\n%d/%d passed" % (p, len(ts)))
    sys.exit(0 if p == len(ts) else 1)
