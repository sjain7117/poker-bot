# Heads-Up Hold'em vs RuleBot

A full-stack heads-up (1v1) No-Limit Texas Hold'em game where you play against
**RuleBot**, an opponent-adaptive poker AI. Python game engine + AI on the
backend (FastAPI), React on the frontend.

Set your stakes, play hands against the bot, and watch a live ledger track who's
up or down across re-buys. The bot reads how _you_ play and adjusts — it punishes
players who over-bet, values calling stations, and steals from folders.

---

## Quick start

You need **Python 3.10+** and **Node.js 18+**. You'll use two terminals — one for
the backend, one for the frontend.

> On macOS, use `python3` and `pip3` (plain `pip` often isn't installed). If any
> command says "command not found," use the `python3 -m ...` form shown below —
> it runs the tool through the interpreter directly and works even when the
> standalone shortcut isn't on your PATH.

### 1. Backend (game engine + AI) — Terminal 1

From the project root:

```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn api.server:app --reload
```

Runs on `http://localhost:8000`. Leave it running.

**Sanity check** that the virtual environment is really active before installing:

```bash
which python3                       # should point INSIDE this project's venv/ folder
```

If it points somewhere else (e.g. `/usr/bin/python3`), re-run
`source venv/bin/activate` and check again.

### 2. Frontend (the table) — Terminal 2

Open a second terminal:

```bash
cd poker-ui
npm install
npm run dev
```

Open the URL it prints (usually `http://localhost:5173`). Pick a buy-in and
stack, hit **Start game**, and play.

> Both must be running at once. If the page says "Can't reach the table," the
> backend in Terminal 1 isn't running.

### Later runs

You only install once. To play again, just re-activate and start each side:

```bash
# Terminal 1
cd ~/poker-ai-engine && source venv/bin/activate && python3 -m uvicorn api.server:app --reload
# Terminal 2
cd ~/poker-ai-engine/poker-ui && npm run dev
```

### Evaluate the bot (optional)

```bash
python3 main.py
```

Plays the bot against baseline opponents and prints its win-rate in bb/100.

---

## Troubleshooting

- **`zsh: command not found: pip` / `uvicorn`** — the venv isn't active or the
  packages aren't installed. Run `source venv/bin/activate`, then install with
  `python3 -m pip install -r requirements.txt`, and start the server with
  `python3 -m uvicorn api.server:app --reload`.
- **`(venv)` shows in the prompt but pip still isn't found** — the environment
  isn't really on your PATH. Re-run `source venv/bin/activate` and confirm with
  `which python3` (it must point inside `venv/`).
- **Browser shows "Method Not Allowed" at `http://localhost:8000/start`** — that's
  expected. `/start` is a POST endpoint the app calls for you; don't open it
  directly in a browser. Use the frontend at `http://localhost:5173`.
- **"Can't reach the table"** — the backend (Terminal 1) isn't running.

---

## How the bot works

RuleBot makes every decision through one pipeline that combines:

| Component                                                    | What it does                                                                                                                                              |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Monte Carlo equity**                                       | Simulates the hand to estimate win probability, weighted by the opponent's likely range.                                                                  |
| **Pot odds / EV**                                            | Computes the price of each action and its expected value.                                                                                                 |
| **Hand strength**                                            | Chen-score preflop percentile; made-hand + draw detection postflop.                                                                                       |
| **Player classification**                                    | Tracks VPIP / PFR / aggression to label you (tight/loose, passive/aggressive) and flag leaks (calling station, nit, over-folder, maniac).                 |
| **Opponent-adaptive ranges**                                 | The crux: a habitual aggressor's bets are treated as _wide_ (so the bot defends and punishes), a passive player's bets as _narrow_ (so it respects them). |
| **Exploitation layer**                                       | Bluffs more vs folders, never vs stations; value-bets bigger vs stations; traps maniacs.                                                                  |
| **Bet sizing / trap mode**                                   | Sizes for value vs bluff; slow-plays monsters against aggressive opponents.                                                                               |
| **Mixed strategy**                                           | Softmax sampling over EV so the bot isn't deterministic and can't be read.                                                                                |
| **Fold equity, position, meta-game, RL nudges, Nash priors** | Additional signals blended into the final decision.                                                                                                       |

### Measured performance (bb/100, 100bb stacks)

| Opponent             | Win-rate |
| -------------------- | -------- |
| Calling station      | ~ +300   |
| Nit                  | ~ +75    |
| Semi-aggressive      | ~ +135   |
| Tight-aggressive     | ~ +500   |
| Maniac (over-bettor) | ~ +1500  |

Decisions take ~9 ms.

### Honest limitations

RuleBot is a strong **heuristic** bot, not a solved GTO solver. It will beat
casual and intermediate players comfortably. The Nash and reinforcement-learning
pieces are lightweight (priors and in-session nudges), and it does not do full
multi-street game-tree search. Natural next steps for a "solver-tier" version
would be real preflop range charts, multi-street lookahead, and a CFR solve for
key spots.

---

## Project structure

```
api/                 FastAPI server (game session, ledger, endpoints)
main.py              Offline evaluation harness (win-rates vs baselines)
src/
  bots/rule_bot.py   The decision engine — orchestrates everything below
  engine/            Betting engine + AI components
    poker_game_engine.py   Correct heads-up NLHE rules, blinds, all-ins
    equity_engine.py       Range-weighted Monte Carlo equity
    opponent_model.py      VPIP/PFR, classification, session profile
    range_model.py         Preflop scoring + adaptive opponent ranges
    ... (hand_strength, fold_equity, bet_sizing, position, etc.)
poker-ui/            React + Vite frontend
```

## Tech stack

Python · FastAPI · Uvicorn · treys (hand evaluation) · React · Vite
