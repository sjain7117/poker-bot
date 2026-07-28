# Heads-Up Hold'em Bot

A playable heads-up (1-vs-1) No-Limit Texas Hold'em web app where a human plays
cash-game hands against **RuleBot**, a rule-based / exploitative poker bot.
Python game engine + decision logic on the backend (FastAPI), React on the
frontend.

Set your stakes, play hands against the bot, and watch a live ledger track who's
up or down across re-buys. The bot estimates equity with Monte Carlo simulation,
compares expected value across its legal actions, and profiles how *you* play
within the session — adjusting its assumptions about your betting range based on
how aggressively you've been playing.

## Quick start

You need **Python 3.10+** and **Node.js 18+**. Two terminals.

### 1. Backend — Terminal 1

    python3 -m venv venv
    source venv/bin/activate
    python3 -m pip install -r requirements.txt
    python3 -m uvicorn api.server:app --reload

Runs on http://localhost:8000 — leave it running.

### 2. Frontend — Terminal 2

    cd poker-ui
    npm install
    npm run dev

Open the URL it prints (usually http://localhost:5173), pick a buy-in and stack,
hit **Start game**, and play.

Both must be running at once. "Can't reach the table" means the backend isn't up.
Opening http://localhost:8000/start in a browser shows "Method Not Allowed" —
that's expected; /start is a POST the app calls for you.

### Tests

    python3 tests/test_engine.py

Covers chip conservation across a hand, legal-action correctness, all-in
uncalled-excess refund, blind/position order, and pot zeroing after settlement.

## How the bot works

| Component | What it does |
|---|---|
| **Monte Carlo equity** (equity_engine) | Simulates the hand to estimate win probability, weighted by the opponent's likely range. |
| **Pot odds / EV** | Required equity to call = to_call / (pot + to_call); expected value computed per legal action. |
| **Hand strength** (hand_strength) | Chen-score preflop percentile; made-hand and draw detection postflop. |
| **Player classification** (opponent_model) | Tracks VPIP / PFR / aggression factor to label the opponent and flag leaks. |
| **Adaptive opponent range** (range_model) | A habitual aggressor's bets are treated as wide, so the bot continues; a passive player's bets as narrow, so it respects them. |
| **Exploitation** (opponent_exploitation, meta_game) | Bluffs more vs folders, less vs stations; traps aggressive opponents. |
| **Bet sizing / trap** (bet_sizing) | Sizes for value vs bluff; slow-plays strong hands against aggressive opponents. |
| **Mixed strategy** (mixed_strategy) | Softmax sampling over EV so the bot isn't deterministic. |
| **Fold equity, position, frequency prior, line labeler** | Additional heuristic signals blended into the final decision. |

EVs are turned into probabilities with a softmax (temperature 0.9), adjusted by
the heuristics above, then sampled. A pot-odds safety net prevents folding a hand
whose equity clearly beats the price.

### Sanity checks (not a benchmark)

During development the bot was played against a handful of trivial scripted
opponents — an always-call script, a check-or-fold script, and a
raise-large-every-hand script — over a few hundred hands each, to confirm it
behaves sensibly: it doesn't fold hands it's a clear favorite with, it calls when
pot odds justify it, and it stops over-folding to a habitual big-raiser as it
gathers reads. These are directional behavior checks against dummy scripts, not a
measured win-rate against real or skilled players, and samples were small.

### Honest scope

RuleBot is a heuristic / exploitative bot, not a game-theory solver. It does not
run CFR/MCCFR, does not compute a Nash equilibrium (the frequency_prior module is
a small fixed table used as a prior), and does not search future streets (the
line_labeler picks a one-street line label). It will beat casual and intermediate
play; it is not claimed to be optimal. Natural next steps: real preflop range
charts, multi-street lookahead, and a CFR solve for specific spots.

## Project structure

    api/                 FastAPI server (game session, ledger, endpoints)
    main.py              Offline harness: play the bot vs scripted baselines
    tests/test_engine.py Engine correctness tests
    src/
      bots/rule_bot.py   Decision engine, orchestrates the components below
      engine/
        poker_game_engine.py   Heads-up NLHE rules, blinds, betting, all-ins
        equity_engine.py       Range-weighted Monte Carlo equity
        hand_strength.py       Chen preflop score + made-hand / draw detection
        range_model.py         Preflop scoring + adaptive opponent ranges
        opponent_model.py      VPIP/PFR/AF, classification, session profile
        fold_equity.py         Fold-equity estimate
        bet_sizing.py          Bet-size selection
        position.py            Position modifiers
        bluff_control.py       Bluff-frequency bookkeeping
        mixed_strategy.py      Line selection / randomization
        meta_game.py           Cross-hand profile nudges
        opponent_exploitation.py  Exploit-score bookkeeping
        frequency_prior.py     Fixed action-frequency prior table
        line_labeler.py        One-street line label (value / bluff / trap)
    poker-ui/            React + Vite frontend

## Tech stack

Python, FastAPI, Uvicorn, treys (hand evaluation), React, Vite

## License

MIT — see LICENSE.
