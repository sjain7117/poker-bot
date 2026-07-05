import { useState, useCallback } from "react";
import "./App.css";

const API = "http://localhost:8000";
const RANKS = "23456789TJQKA";

/* ---------- card ---------- */
function Card({ label, size = "md" }) {
  const isBack = !label || !RANKS.includes(label[0]);
  if (isBack) return <div className={`card card--back card--${size}`} />;
  const rank = label.slice(0, -1);
  const suit = label.slice(-1);
  const red = suit === "♥" || suit === "♦";
  return (
    <div className={`card card--${size} ${red ? "card--red" : ""}`}>
      <span className="card__rank">{rank}</span>
      <span className="card__suit">{suit}</span>
    </div>
  );
}

function Slot() {
  return <div className="card card--md card--slot" />;
}

/* ---------- money helpers ---------- */
const money = (n) =>
  (n < 0 ? "-$" : "$") +
  Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 });

/* ---------- setup screen ---------- */
function Setup({ onStart, busy }) {
  const [stack, setStack] = useState(200);
  const [buyin, setBuyin] = useState(100);
  return (
    <div className="setup">
      <div className="setup__brand">HEADS-UP HOLD'EM</div>
      <div className="setup__sub">
        Set your stakes, then take a seat against RuleBot.
      </div>

      <div className="setup__field">
        <label>Buy-in value</label>
        <div className="setup__row">
          {[20, 50, 100, 200].map((v) => (
            <button
              key={v}
              className={`chip-opt ${buyin === v ? "on" : ""}`}
              onClick={() => setBuyin(v)}
            >
              ${v}
            </button>
          ))}
        </div>
      </div>

      <div className="setup__field">
        <label>Starting stack (chips per buy-in)</label>
        <div className="setup__row">
          {[100, 200, 500, 1000].map((v) => (
            <button
              key={v}
              className={`chip-opt ${stack === v ? "on" : ""}`}
              onClick={() => setStack(v)}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      <div className="setup__note">
        Blinds are 1 / 2. Bust to zero and you auto re-buy for {money(buyin)} —
        the ledger keeps score.
      </div>

      <button
        className="btn btn--primary setup__go"
        disabled={busy}
        onClick={() => onStart(stack, buyin)}
      >
        {busy ? "Dealing…" : "Start game"}
      </button>
    </div>
  );
}

/* ---------- seat ---------- */
function Seat({ name, emoji, chips, isButton, commit, folded }) {
  return (
    <div className={`seat ${folded ? "seat--folded" : ""}`}>
      <div className="seat__avatar">
        {emoji}
        {isButton && <span className="dealer">D</span>}
      </div>
      <div className="seat__name">{name}</div>
      <div className="seat__chips">{chips}</div>
      {commit > 0 && <div className="seat__bet">{commit}</div>}
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState("setup");
  const [s, setS] = useState(null);
  const [bet, setBet] = useState(0);
  const [busy, setBusy] = useState(false);

  const call = useCallback(async (path, body) => {
    setBusy(true);
    try {
      const res = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json();
      setS(data);
      setBet(0);
      return data;
    } catch {
      setS({ error: "Can't reach the table. Is the server running on :8000?" });
    } finally {
      setBusy(false);
    }
  }, []);

  const startGame = async (stack, buyin) => {
    const data = await call("/start", { stack, buyin });
    if (data && !data.error) setScreen("table");
  };
  const act = (kind, amount = null) => call("/action", { kind, amount });
  const next = () => call("/next");
  const stop = async () => {
    await call("/stop");
  };

  if (screen === "setup")
    return (
      <div className="app">
        {s?.error && <div className="toast">{s.error}</div>}
        <Setup onStart={startGame} busy={busy} />
      </div>
    );

  if (!s)
    return (
      <div className="app">
        <div className="loading">Dealing…</div>
      </div>
    );
  if (s.error)
    return (
      <div className="app">
        <div className="panel">
          {s.error}
          <button className="btn" onClick={() => setScreen("setup")}>
            Back
          </button>
        </div>
      </div>
    );

  const legal = s.legal || {};
  const acts = legal.actions || [];
  const raiseSpec = legal.raise || legal.bet;
  const canRaise = acts.includes("raise");
  const heroTurn = s.to_act === "hero" && !s.hand_over;
  const betMin = raiseSpec ? raiseSpec.min_to : 0;
  const betVal = bet > 0 ? bet : betMin;
  const quick = (frac) => {
    if (!raiseSpec) return;
    const target = Math.round((s.street_commit?.hero || 0) + frac * s.pot);
    setBet(Math.max(raiseSpec.min_to, Math.min(target, raiseSpec.max_to)));
  };

  const L = s.ledger || {};
  const result = s.result;
  const heroWon =
    result && (result.winner === "hero" || result.winner === "split");
  const stopped = s.phase === "stopped";

  const netTag = (v) => (
    <span className={`net ${v > 0 ? "up" : v < 0 ? "down" : ""}`}>
      {v > 0 ? "▲" : v < 0 ? "▼" : "—"} {money(v)}
    </span>
  );

  return (
    <div className="app">
      {/* top bar */}
      <div className="topbar">
        <button className="link" onClick={() => setScreen("setup")}>
          ‹ Lobby
        </button>
        <div className="topbar__stakes">
          {money(s.stakes.buyin)} buy-in · {s.stakes.stack} stack · blinds{" "}
          {s.stakes.sb}/{s.stakes.bb}
        </div>
        <button className="link" onClick={stop} disabled={stopped}>
          End game
        </button>
      </div>

      <div className="felt">
        {/* opponent seat */}
        <div className="felt__top">
          <Seat
            name="RuleBot"
            emoji="🤖"
            chips={s.stacks.bot}
            isButton={s.button === "bot"}
            commit={s.street_commit?.bot}
            folded={false}
          />
          {s.hand_over && s.result?.reason === "showdown" && (
            <div className="reveal">
              <div className="reveal__cards">
                {(s.bot_cards || []).map((c, i) => (
                  <Card key={i} label={c} size="sm" />
                ))}
              </div>
              <div className="reveal__label">{s.bot_hand_label || ""}</div>
            </div>
          )}
        </div>

        {/* board + pot */}
        <div className="board-wrap">
          <div className="board">
            {(s.board || []).map((c, i) => (
              <Card key={i} label={c} size="md" />
            ))}
            {Array.from({ length: 5 - (s.board?.length || 0) }).map((_, i) => (
              <Slot key={"s" + i} />
            ))}
          </div>
          <div className="pot">
            <span className="pot__label">POT</span>
            <span className="pot__val">{s.pot}</span>
          </div>
        </div>

        {/* hero */}
        <div className="felt__bottom">
          <div className="hero-hand">
            {(s.hero_cards || []).map((c, i) => (
              <Card key={i} label={c} size="lg" />
            ))}
          </div>
          <div className="hero-info">
            <div className="hero-info__label">{s.hero_hand_label || "—"}</div>
            <div className="hero-info__seat">
              <span className="seat__avatar sm">
                🧑{s.button === "hero" && <span className="dealer">D</span>}
              </span>
              <span className="hero-info__chips">{s.stacks.hero}</span>
            </div>
          </div>
        </div>
      </div>

      {/* controls */}
      <div className="controls">
        {stopped ? (
          <div className="endcard">
            <div className="endcard__title">Session ended</div>
            <button
              className="btn btn--primary"
              onClick={() => setScreen("setup")}
            >
              New game
            </button>
          </div>
        ) : s.hand_over ? (
          <div className="result">
            <div className={`result__who ${heroWon ? "up" : "down"}`}>
              {result?.winner === "split"
                ? "Split pot"
                : heroWon
                  ? "You win " + result.pot
                  : "RuleBot wins " + result.pot}
            </div>
            <div className="result__hands">
              <span className="result__hand">
                You had{" "}
                <b>
                  {(
                    result?.hero_class ||
                    s.hero_hand_label ||
                    "high card"
                  ).toLowerCase()}
                </b>
              </span>
              {result?.reason === "showdown" && result?.bot_class && (
                <span className="result__hand">
                  RuleBot had <b>{result.bot_class.toLowerCase()}</b>
                </span>
              )}
            </div>
            <div className="result__why">
              {s.last_bust
                ? `${s.last_bust === "hero" ? "You" : "RuleBot"} re-bought · `
                : ""}
              {result?.reason === "fold" ? "opponent folded" : "showdown"}
            </div>
            <button className="btn btn--primary" onClick={next} disabled={busy}>
              Next hand
            </button>
          </div>
        ) : heroTurn ? (
          <>
            <div className="pills">
              {acts.includes("fold") && (
                <button
                  className="btn"
                  onClick={() => act("fold")}
                  disabled={busy}
                >
                  Fold
                </button>
              )}
              {acts.includes("check") && (
                <button
                  className="btn"
                  onClick={() => act("check")}
                  disabled={busy}
                >
                  Check
                </button>
              )}
              {acts.includes("call") && (
                <button
                  className="btn"
                  onClick={() => act("call")}
                  disabled={busy}
                >
                  Call {legal.call_amount}
                </button>
              )}
              {raiseSpec && (
                <button
                  className="btn btn--primary"
                  onClick={() => act(canRaise ? "raise" : "bet", betVal)}
                  disabled={busy}
                >
                  {canRaise ? "Raise to" : "Bet"} {betVal}
                </button>
              )}
            </div>
            {raiseSpec && (
              <div className="sizer">
                <input
                  type="range"
                  min={raiseSpec.min_to}
                  max={raiseSpec.max_to}
                  value={betVal}
                  onChange={(e) => setBet(Number(e.target.value))}
                />
                <div className="sizer__quick">
                  <button onClick={() => quick(0.5)}>½ pot</button>
                  <button onClick={() => quick(0.75)}>¾ pot</button>
                  <button onClick={() => quick(1)}>Pot</button>
                  <button onClick={() => setBet(raiseSpec.max_to)}>
                    All-in
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="waiting">RuleBot is thinking…</div>
        )}
      </div>

      {/* ledger */}
      <div className="ledger">
        <div className="ledger__row">
          <span className="ledger__name">🧑 You</span>
          <span className="ledger__buys">{L.hero?.buyins}× buy-in</span>
          {netTag(L.hero?.net || 0)}
        </div>
        <div className="ledger__row">
          <span className="ledger__name">🤖 RuleBot</span>
          <span className="ledger__buys">{L.bot?.buyins}× buy-in</span>
          {netTag(L.bot?.net || 0)}
        </div>
        <div className="ledger__meta">{s.hands_played} hands played</div>
      </div>
    </div>
  );
}
