import { useEffect, useMemo, useState } from "react";

const RED = "#ff2d1f";
const AMBER = "#ffb000";
const CYAN = "#00e5ff";

const CASES = [
  {
    id: 1,
    code: "CASE 01",
    title: "WIRE TRANSFER",
    risk: "HIGH RISK",
    attrs: ["$70,000", "NEW ACCOUNT", "PASSWORD RESET", "UNKNOWN DEVICE"],
    isFraud: true,
    explanation: "High-value transfer after password reset to a new account. Strong account-takeover pattern.",
  },
  {
    id: 2,
    code: "CASE 02",
    title: "ONLINE PURCHASE",
    risk: "LOW RISK",
    attrs: ["$120", "KNOWN DEVICE", "LOCAL IP", "NORMAL CADENCE"],
    isFraud: false,
    explanation: "Known device, local location, and expected spend behavior. No meaningful anomaly.",
  },
  {
    id: 3,
    code: "CASE 03",
    title: "LOGIN ATTEMPT",
    risk: "CRITICAL",
    attrs: ["FOREIGN IP", "NEW DEVICE", "ODD HOURS", "PASSWORD CHANGE"],
    isFraud: true,
    explanation: "Geo, timing, and device anomalies combine into a strong takeover signal.",
  },
];

const LEADERBOARD = [
  ["AAA", 2480],
  ["BOT", 2310],
  ["ZEN", 2190],
  ["YOU", 0],
  ["RDX", 1720],
];

export default function App() {
  const [page, setPage] = useState("cases");
  const [answers, setAnswers] = useState({});
  const [time, setTime] = useState(60);
  const [shownScore, setShownScore] = useState(0);
  const [open, setOpen] = useState({});
  const [pulse, setPulse] = useState(null);

  useEffect(() => {
    if (page !== "cases") return;
    if (time <= 0) return setPage("results");
    const t = setTimeout(() => setTime((v) => v - 1), 1000);
    return () => clearTimeout(t);
  }, [time, page]);

  const choose = (id, answer) => {
    setAnswers((prev) => ({ ...prev, [id]: answer }));
    setPulse(id);
    setTimeout(() => setPulse(null), 220);
  };

  const score = useMemo(() => {
    return CASES.reduce((sum, c) => {
      if (!answers[c.id]) return sum;
      return sum + (((answers[c.id] === "fraud") === c.isFraud) ? 100 : 0);
    }, 0);
  }, [answers]);

  useEffect(() => {
    if (page !== "results") return;
    let current = 0;
    const step = Math.max(1, Math.ceil(score / 18));
    const timer = setInterval(() => {
      current += step;
      if (current >= score) {
        current = score;
        clearInterval(timer);
      }
      setShownScore(current);
    }, 28);
    return () => clearInterval(timer);
  }, [page, score]);

  const humansScore = page === "results" ? 1082 + score : 1082;
  const playerWon = score >= 200;

  const ArcadeFrame = ({ children }) => (
    <div className="min-h-screen overflow-hidden bg-black text-white relative">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,45,31,0.32),transparent_36%),radial-gradient(circle_at_12%_28%,rgba(0,229,255,0.16),transparent_28%),radial-gradient(circle_at_88%_34%,rgba(255,176,0,0.12),transparent_30%)]" />
      <div className="absolute inset-0 opacity-[0.07] bg-[linear-gradient(rgba(255,255,255,0.8)_1px,transparent_1px)] bg-[length:100%_4px]" />
      <div className="relative z-10 max-w-7xl mx-auto px-8 py-7">{children}</div>
    </div>
  );

  const HeaderScoreboard = () => (
    <div className="mb-8">
      <div className="flex items-end justify-between gap-8">
        <div>
          <div className="text-[13px] tracking-[0.45em] text-gray-400 font-black">FRAUD BUSTER</div>
          <div className="text-5xl md:text-7xl font-black leading-none tracking-[-0.06em] mt-1">
            BEAT THE AI
          </div>
        </div>

        <div className="text-right">
          <div className="text-[11px] tracking-[0.35em] text-gray-400 font-black">TIME</div>
          <div className={`text-6xl font-black leading-none ${time <= 10 && page === "cases" ? "animate-pulse" : ""}`} style={{ color: time <= 10 ? AMBER : "white" }}>
            {String(time).padStart(2, "0")}
          </div>
        </div>
      </div>

      <div className="mt-7 grid grid-cols-[1fr_auto_1fr] items-center gap-5">
        <div className="rounded-[2rem] border border-red-500/40 bg-red-500/10 p-6 shadow-[0_0_50px_rgba(255,45,31,0.20)]">
          <div className="text-[12px] tracking-[0.4em] text-red-200 font-black">AI SCORE</div>
          <div className="text-7xl md:text-8xl font-black leading-none tracking-[-0.08em]" style={{ color: RED }}>1248</div>
        </div>

        <div className="text-4xl md:text-6xl font-black text-gray-500">VS</div>

        <div className="rounded-[2rem] border border-cyan-300/40 bg-cyan-300/10 p-6 text-right shadow-[0_0_50px_rgba(0,229,255,0.15)]">
          <div className="text-[12px] tracking-[0.4em] text-cyan-100 font-black">HUMANS</div>
          <div className="text-7xl md:text-8xl font-black leading-none tracking-[-0.08em]" style={{ color: CYAN }}>{humansScore}</div>
        </div>
      </div>

      <div className="mt-5 h-3 rounded-full bg-white/10 overflow-hidden border border-white/10">
        <div className="h-full rounded-full shadow-[0_0_25px_rgba(255,45,31,0.8)]" style={{ width: `${Math.min(100, (time / 60) * 100)}%`, background: time <= 10 ? AMBER : RED }} />
      </div>
    </div>
  );

  const LeaderboardPanel = () => (
    <div className="fixed left-6 top-7 bottom-7 z-20 w-[220px] rounded-[2rem] border border-white/10 bg-white/[0.06] p-5 backdrop-blur-xl shadow-[0_0_60px_rgba(0,0,0,0.45)]">
      <div className="text-[11px] tracking-[0.4em] text-gray-500 font-black mb-5">LEADERBOARD</div>
      <div className="space-y-3">
        {LEADERBOARD.map(([name, points], index) => (
          <div
            key={name}
            className={`rounded-2xl border px-4 py-3 ${name === "YOU" ? "border-red-400/60 bg-red-500/15" : "border-white/10 bg-black/25"}`}
          >
            <div className="flex items-center justify-between">
              <div className="text-[10px] tracking-[0.25em] text-gray-500 font-black">#{index + 1}</div>
              <div className="text-[10px] text-gray-500 font-black">{points}</div>
            </div>
            <div className="mt-1 text-2xl font-black leading-none" style={name === "YOU" ? { color: RED } : {}}>{name}</div>
          </div>
        ))}
      </div>
    </div>
  );

  const CaseTile = ({ c }) => {
    const selected = answers[c.id];
    return (
      <div className={`group relative rounded-[2rem] p-[1px] transition duration-200 ${pulse === c.id ? "scale-[1.04]" : "hover:scale-[1.02]"}`}>
        <div className="absolute inset-0 rounded-[2rem] bg-gradient-to-br from-white/35 via-white/5 to-transparent opacity-70" />
        <div className="relative rounded-[2rem] bg-zinc-950/95 border border-white/10 p-6 min-h-[355px] shadow-2xl">
          <div className="flex justify-between items-start mb-7">
            <div>
              <div className="text-[11px] tracking-[0.35em] text-gray-500 font-black">{c.code}</div>
              <div className="text-3xl font-black tracking-[-0.05em] leading-none mt-2">{c.title}</div>
            </div>
            <div className="px-3 py-1 rounded-full text-[10px] font-black tracking-[0.2em] border" style={{ color: c.risk === "LOW RISK" ? CYAN : AMBER, borderColor: c.risk === "LOW RISK" ? CYAN : AMBER }}>
              {c.risk}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-8">
            {c.attrs.map((a) => (
              <div key={a} className="rounded-2xl bg-white/[0.07] border border-white/10 px-4 py-3">
                <div className="text-sm font-black text-white/90">{a}</div>
              </div>
            ))}
          </div>

          <div className="absolute left-6 right-6 bottom-6 grid grid-cols-2 gap-3">
            <button
              onClick={() => choose(c.id, "legit")}
              className={`py-4 rounded-2xl font-black tracking-wide transition ${selected === "legit" ? "bg-white text-black shadow-[0_0_25px_rgba(255,255,255,0.38)]" : "bg-white/10 text-white hover:bg-white/20"}`}
            >
              LEGIT
            </button>
            <button
              onClick={() => choose(c.id, "fraud")}
              className={`py-4 rounded-2xl font-black tracking-wide transition ${selected === "fraud" ? "text-white shadow-[0_0_30px_rgba(255,45,31,0.6)]" : "bg-red-500/20 text-red-100 hover:bg-red-500/30"}`}
              style={selected === "fraud" ? { background: RED } : {}}
            >
              FRAUD
            </button>
          </div>
        </div>
      </div>
    );
  };

  const ReviewRow = ({ c }) => {
    const correct = (answers[c.id] === "fraud") === c.isFraud;
    return (
      <div className="rounded-[1.75rem] border border-white/10 bg-white/[0.06] p-5">
        <div className="flex items-center justify-between gap-6">
          <div className="min-w-0">
            <div className="text-[11px] tracking-[0.35em] text-gray-500 font-black">{c.code}</div>
            <div className="text-2xl font-black tracking-[-0.04em]">{c.title}</div>
            <div className="text-sm text-gray-400 mt-1">YOU: {answers[c.id]?.toUpperCase() || "NO ANSWER"} · CORRECT: {c.isFraud ? "FRAUD" : "LEGIT"}</div>
          </div>
          <div className="flex items-center gap-5">
            <div className="text-4xl font-black" style={{ color: correct ? CYAN : RED }}>{correct ? "+100" : "+0"}</div>
            <button
              onClick={() => setOpen((p) => ({ ...p, [c.id]: !p[c.id] }))}
              className="px-5 py-3 rounded-2xl border border-red-400/50 text-sm font-black tracking-wide hover:bg-red-500/15 transition"
              style={{ color: RED }}
            >
              AI EXPLAIN
            </button>
          </div>
        </div>
        {open[c.id] && (
          <div className="mt-4 rounded-2xl bg-black/40 border border-white/10 p-4 text-gray-300">
            {c.explanation}
          </div>
        )}
      </div>
    );
  };

  return (
    <ArcadeFrame>
      <LeaderboardPanel />
      <div className="pl-[250px]">
      <HeaderScoreboard />

      {page === "cases" && (
        <>
          <div className="grid grid-cols-3 gap-6">
            {CASES.map((c) => <CaseTile key={c.id} c={c} />)}
          </div>
          <div className="mt-10 flex justify-center">
            <button
              onClick={() => setPage("results")}
              className="px-14 py-5 rounded-[1.5rem] text-2xl font-black tracking-wide text-white transition hover:scale-110 active:scale-95 shadow-[0_0_55px_rgba(255,45,31,0.55)]"
              style={{ background: RED }}
            >
              LOCK IN ANSWERS
            </button>
          </div>
        </>
      )}

      {page === "results" && (
        <>
          <div className="text-center mb-8 rounded-[2rem] border border-white/10 bg-white/[0.05] py-8 shadow-[0_0_70px_rgba(255,45,31,0.12)]">
            <div className="text-[12px] tracking-[0.5em] text-gray-400 font-black">{score >= 200 ? "HUMAN VICTORY" : "AI VICTORY"}</div>
            <div className="text-9xl font-black tracking-[-0.09em] leading-none mt-2" style={{ color: RED }}>{shownScore}</div>
            <div className="text-xl font-black mt-2">PLAYER SCORE</div>
          </div>

          <div className="space-y-4">
            {CASES.map((c) => <ReviewRow key={c.id} c={c} />)}
          </div>

          <div className="mt-9 flex justify-center">
            <button
              onClick={() => window.location.reload()}
              className="px-10 py-4 rounded-2xl bg-white text-black font-black hover:scale-105 transition"
            >
              PLAY AGAIN
            </button>
          </div>
        </>
      )}
      </div>
    </ArcadeFrame>
  );
}
