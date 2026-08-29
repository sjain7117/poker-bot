"""
api/server.py — Heads-up poker server: you vs the RuleBot.

A "game" is a cash session at fixed stakes you choose up front (a buy-in value
and a starting stack). Both seats start with one buy-in. Whenever a seat busts
to zero it automatically re-buys for another full stack, and the ledger tracks
each seat's buy-ins, current chips, and net cash position so you always know
who's actually up or down across re-buys.

Every request carries an X-Session-Id header identifying one player's table,
so concurrent players never share a game. Sessions are held in memory and are
dropped after SESSION_TTL_SECONDS of inactivity, or when MAX_SESSIONS is
exceeded (oldest first). A request for a session that no longer exists gets a
409 rather than a silently regenerated game.

Endpoints:
  GET  /health                   liveness, does not create a session
  POST /start   {stack, buyin}   begin a new session at these stakes
  POST /action  {kind, amount?}  you act; the bot auto-plays to your next turn
  POST /next                     deal the next hand (re-buys a busted seat)
  POST /stop                     end the session (returns final ledger)
  GET  /state                    current state
"""
import os
import threading
import time
import uuid
from collections import OrderedDict

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from treys import Card

from src.engine.poker_game_engine import PokerGameEngine, HERO, BOT

from src.bots.rule_bot import RuleBot

SB, BB = 1, 2
SUITS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}


def _int_env(name, default, minimum=None):
    """Read an int env var, falling back to the default if it is malformed.

    A typo in the Render dashboard should not take the service down with a
    traceback at import time.
    """
    try:
        val = int(os.environ[name])
    except (KeyError, ValueError):
        val = default
    if minimum is not None and val < minimum:
        val = minimum
    return val


SESSION_TTL = _int_env("SESSION_TTL_SECONDS", 3600)
MAX_SESSIONS = _int_env("MAX_SESSIONS", 200, minimum=1)
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Session-Id"],
)


def show(cards):
    out = []
    for c in cards:
        s = Card.int_to_str(c)
        out.append(s[0] + SUITS[s[1]])
    return out


class StartReq(BaseModel):
    stack: int = 200
    buyin: float = 100.0


class Action(BaseModel):
    kind: str
    amount: Optional[int] = None


class GameSession:
    def __init__(self, stack=200, buyin=100.0):
        self.stack_size = max(20, int(stack))
        self.buyin_value = float(buyin)
        self.table = PokerGameEngine(self.stack_size, SB, BB)
        self.bot = RuleBot("RuleBot")
        self.buyins = {"hero": 1, "bot": 1}
        self.hands_played = 0
        self.last_bust = None            # who re-bought most recently
        self.bot_log = []
        self.stopped = False
        self.new_hand()

    # ------------------------------------------------------------------ #
    def _rebuy_if_needed(self):
        self.last_bust = None
        for idx, name in ((HERO, "hero"), (BOT, "bot")):
            if self.table.stacks[idx] <= 0:
                self.table.stacks[idx] = self.stack_size
                self.buyins[name] += 1
                self.last_bust = name

    def new_hand(self):
        if self.stopped:
            return
        self._rebuy_if_needed()
        self.bot_log = []
        self.table.start_hand()
        self.bot.new_hand("hero")
        self.hands_played += 1
        self._run_bot()

    def _run_bot(self):
        t = self.table
        guard = 0
        while (not t.done and t.to_act == BOT
               and t.street not in ("showdown", "done") and guard < 30):
            guard += 1
            d = self.bot.decide(t.view_for(BOT, "hero"))
            self.bot_log.append({
                "action": d["action"], "amount": d.get("amount"),
                "reason": d["reason"], "equity": d["equity"],
                "read": d["debug"].get("opp_style"),
                "leaks": d["debug"].get("leaks", []),
            })
            t.apply_action(d["action"], d.get("amount"))
        if t.done:
            self._settle()

    def hero_action(self, kind, amount):
        t = self.table
        if t.done or t.to_act != HERO or self.stopped:
            return
        self.bot.observe_opponent_action("hero", kind, t.street)
        t.apply_action(kind, amount)
        if t.done:
            self._settle()
        else:
            self._run_bot()

    def _settle(self):
        reward = self.table.stacks[BOT] - self.stack_size
        self.bot.settle_hand(reward)

    # ------------------------------------------------------------------ #
    def ledger(self):
        out = {}
        for idx, name in ((HERO, "hero"), (BOT, "bot")):
            chips = self.table.stacks[idx]
            invested = self.buyins[name] * self.buyin_value
            value = chips / self.stack_size * self.buyin_value
            out[name] = {
                "buyins": self.buyins[name],
                "chips": chips,
                "invested": round(invested, 2),
                "net": round(value - invested, 2),
            }
        return out

    def _hand_label(self, idx):
        t = self.table
        if len(t.board) < 3 or not t.hole[idx]:
            return None
        try:
            score = t.evaluator.evaluate(t.board, t.hole[idx])
            return t.evaluator.class_to_string(t.evaluator.get_rank_class(score))
        except Exception:
            return None

    def state(self):
        t = self.table
        legal = t.legal_actions()
        over = t.done or t.street in ("showdown", "done")
        reveal = over
        return {
            "phase": "stopped" if self.stopped else "playing",
            "stakes": {"stack": self.stack_size, "buyin": self.buyin_value,
                       "sb": SB, "bb": BB},
            "hand_no": t.hand_no,
            "hands_played": self.hands_played,
            "street": t.street,
            "pot": t.pot + sum(t.street_commit),
            "board": show(t.board),
            "hero_cards": show(t.hole[HERO]),
            "bot_cards": show(t.hole[BOT]) if reveal else ["**", "**"],
            "hero_hand_label": self._hand_label(HERO),
            "bot_hand_label": self._hand_label(BOT) if reveal else None,
            "stacks": {"hero": t.stacks[HERO], "bot": t.stacks[BOT]},
            "street_commit": {"hero": t.street_commit[HERO],
                              "bot": t.street_commit[BOT]},
            "button": "hero" if t.button == HERO else "bot",
            "to_act": ("hero" if t.to_act == HERO else "bot") if not over else None,
            "legal": self._hero_legal(legal) if (not over and t.to_act == HERO) else None,
            "bot_log": self.bot_log,
            "hand_over": over,
            "result": t.result if over else None,
            "last_bust": self.last_bust,
            "opp_class": self.bot.opponent("hero").style,
            "opp_leaks": list(self.bot.opponent("hero").leaks),
            "opp_stats": {
                "vpip": round(self.bot.opponent("hero").vpip, 2),
                "pfr": round(self.bot.opponent("hero").pfr, 2),
                "af": round(self.bot.opponent("hero").af, 2),
            },
            "ledger": self.ledger(),
        }

    def _hero_legal(self, legal):
        out = {"actions": legal.get("actions", [])}
        for k in ("call_amount", "to_call", "bet", "raise"):
            if k in legal:
                out[k] = legal[k]
        return out


_lock = threading.Lock()
_sessions = OrderedDict()

EXPIRED = {
    "error": "Session expired. The free server sleeps after 15 minutes idle, "
             "which clears any game in progress. Start a new game.",
    "expired": True,
}


def _sweep(now):
    dead = [sid for sid, (_, seen) in _sessions.items() if now - seen > SESSION_TTL]
    for sid in dead:
        del _sessions[sid]
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)


def _get(sid):
    now = time.time()
    _sweep(now)
    if not sid or sid not in _sessions:
        return None
    game, _ = _sessions[sid]
    _sessions[sid] = (game, now)
    _sessions.move_to_end(sid)
    return game


def _put(sid, game):
    now = time.time()
    _sessions[sid] = (game, now)
    _sessions.move_to_end(sid)
    _sweep(now)


def _expired():
    return JSONResponse(status_code=409, content=EXPIRED)


def _reply(sid, game):
    payload = game.state()
    payload["session_id"] = sid
    return payload


@app.get("/health")
def health():
    with _lock:
        return {"ok": True, "sessions": len(_sessions)}


@app.post("/start")
def start(req: StartReq, x_session_id: Optional[str] = Header(default=None)):
    sid = x_session_id or uuid.uuid4().hex
    with _lock:
        game = GameSession(stack=req.stack, buyin=req.buyin)
        _put(sid, game)
        return _reply(sid, game)


@app.post("/action")
def action(a: Action, x_session_id: Optional[str] = Header(default=None)):
    with _lock:
        game = _get(x_session_id)
        if game is None:
            return _expired()
        game.hero_action(a.kind, a.amount)
        return _reply(x_session_id, game)


@app.post("/next")
def next_hand(x_session_id: Optional[str] = Header(default=None)):
    with _lock:
        game = _get(x_session_id)
        if game is None:
            return _expired()
        if not game.stopped:
            game.table.end_hand_and_rotate()
            game.new_hand()
        return _reply(x_session_id, game)


@app.post("/stop")
def stop(x_session_id: Optional[str] = Header(default=None)):
    with _lock:
        game = _get(x_session_id)
        if game is None:
            return _expired()
        game.stopped = True
        return _reply(x_session_id, game)


@app.get("/state")
def state(x_session_id: Optional[str] = Header(default=None)):
    with _lock:
        game = _get(x_session_id)
        if game is None:
            return _expired()
        return _reply(x_session_id, game)
