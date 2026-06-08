import os
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
import zipfile
from typing import Dict, List, Optional, Tuple, Union

import streamlit as st

try:
    import oracledb
except Exception:  # pragma: no cover - lets the UI run without the driver installed
    oracledb = None


# ==========================================================
# Fraud Buster Challenge
# Streamlit + Oracle Autonomous Database
# ==========================================================

APP_TITLE = "Fraud Buster Challenge"
APP_SUBTITLE = "Can You Beat AI at Enterprise Decisions?"
INDUSTRIES = [
    "Banking/Finance",
    "Insurance",
    "Telco & Technology",
    "Healthcare",
    "Industrial",
    "Government",
]

RED = "#ff2d1f"
AMBER = "#ffb000"
CYAN = "#00e5ff"
ORACLE_RED = "#c74634"
CHALLENGE_SECONDS = 60
CASES_PER_SESSION = 3


@dataclass
class Case:
    case_id: int
    industry: str
    scenario_type: str
    name: str
    attributes: List[str]
    is_fraud: bool
    explanation: str


def init_state() -> None:
    defaults = {
        "page": "landing",
        "player_id": None,
        "session_id": None,
        "player_name": "",
        "company": "",
        "industry": INDUSTRIES[0],
        "cases": [],
        "answers": {},
        "confidence": {},
        "case_times": {},
        "start_time": None,
        "submitted": False,
        "score_saved": False,
        "result": None,
        "ai_result": None,
        "select_ai_available": True,
        "event_question": "",
        "event_answer": "",
        "performance_summary": "",
        "performance_summary_requested": False,
        "performance_summary_pending": False,
        "case_explanations": {},
        "explanation_requested": {},
        "explanation_pending": {},
        "db_error": None,
        "show_reg": False,
        "force_submit": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def select_ai(prompt: str, action: str = "chat") -> str:
    """Run a brief Select AI prompt through the Fraud Buster AI profile.

    DBMS_CLOUD_AI.GENERATE is used because it works cleanly from application code
    without depending on SQL worksheet-style SELECT AI parsing.
    """
    try:
        conn = get_active_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DBMS_CLOUD_AI.GENERATE(
                    prompt       => :prompt,
                    profile_name => 'FRAUD_BUSTER_AI',
                    action       => :action
                )
                FROM dual
                """,
                {"prompt": prompt, "action": action},
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                st.session_state.select_ai_available = True
                return str(row[0]).strip()
            raise RuntimeError("Select AI returned no response.")
    except Exception as exc:
        st.session_state.select_ai_available = False
        st.session_state.db_error = f"Select AI notice: {exc}"
        raise


def fallback_case_explanation(case: Case, selected: str, correct: bool) -> str:
    correct_answer = "Fraud" if case.is_fraud else "Legit"
    shown_signals = ", ".join(case.attributes[:3]) if case.attributes else "No additional signals"
    outcome = "correctly identified" if correct else "missed"
    return (
        f"Correct answer: {correct_answer}. The player {outcome} this case. "
        f"Key signal: {case.attributes[0] if case.attributes else case.scenario_type}. "
        f"Supporting signals: {shown_signals}. Reason: {case.explanation}"
    )


def get_case_ai_explanation(case: Case, info: Dict[str, Union[int, bool, str]]) -> str:
    cached = st.session_state.case_explanations.get(case.case_id)
    if cached:
        return cached

    selected = str(info.get("selected", "No Answer"))
    correct = bool(info.get("correct", False))
    prompt = f"""
Explain this Fraud Buster game case briefly for a booth player.
Case ID: {case.case_id}
Industry: {case.industry}
Scenario type: {case.scenario_type}
Subject: {case.name}
Scenario: {case.attributes[0] if case.attributes else ''}
Other signals: {', '.join(case.attributes[1:])}
Player selected: {selected}
Correct answer: {'Fraud' if case.is_fraud else 'Legit'}
Score: {info.get('total', 0)}
Give 2 to 4 short sentences covering the reason, main signals, and what the player should learn.
""".strip()
    try:
        explanation = select_ai(prompt)
    except Exception:
        explanation = fallback_case_explanation(case, selected, correct)
    st.session_state.case_explanations[case.case_id] = explanation
    return explanation


def get_performance_summary(result: Dict) -> str:
    cached = st.session_state.performance_summary
    if cached:
        return cached

    lines = []
    for case in st.session_state.cases:
        info = result["case_scores"][case.case_id]
        lines.append(
            f"Case {case.case_id} {case.scenario_type}: selected {info['selected']}, "
            f"correct answer {'Fraud' if case.is_fraud else 'Legit'}, score {info['total']}."
        )
    prompt = f"""
Summarize this Fraud Buster player performance in 3 short sentences.
Player: {st.session_state.player_name}
Company: {st.session_state.company}
Industry: {st.session_state.industry}
Total score: {result['total_score']}
Total time: {result['total_time']} seconds
Outcome: {'Human beat AI' if result['human_won'] else 'AI won'}
Cases: {' '.join(lines)}
Keep it brief and booth-friendly.
""".strip()
    try:
        summary = select_ai(prompt)
    except Exception:
        ai_score = st.session_state.ai_result["total_score"] if st.session_state.ai_result else "AI"
        summary = (
            f"{st.session_state.player_name} scored {result['total_score']} points in {result['total_time']} seconds. "
            f"The result was {'a Human win' if result['human_won'] else 'an AI win'} against the {ai_score}-point AI performance. "
            "Review the case explanations to see which risk signals mattered most."
        )
    st.session_state.performance_summary = summary
    return summary

# ASK SELECT AI Prompt

def answer_event_question(question: str) -> str:
    prompt = f"""
Answer this Fraud Buster Challenge event question using these tables:
- PLAYERS (NAME, COMPANY, INDUSTRY)
- LEADERBOARD (PLAYER_ID, SCORE, TOTAL_TIME, PLAYER_TYPE, SESSION_ID)
- CASES (CASE_ID, INDUSTRY, SCENARIO_TYPE, IS_FRAUD)
- PLAYER_CASE_RESULTS (PLAYER_ID, CASE_ID, IS_CORRECT, CONFIDENCE, ACTOR_TYPE)

Rules:
1. Top Player: 'HUMAN' with highest SCORE in LEADERBOARD.
2. Human Win: Session where HUMAN score >= AI score for same SESSION_ID.
3. Win Rate: (Total Human Wins / Total Human Sessions) * 100.
4. Accuracy: (Count of IS_CORRECT='Y' / Total decisions) * 100.
5. Consolidated Points: SUM of SCORE for a company or industry.
6. Scenarios: Use CASES.SCENARIO_TYPE for names like 'Wire Transfer'.
7. DATA ACCURACY: Report EXACT numerical values from the database. Do not round, estimate, or invent numbers.
8. SCOPE: If a question is unrelated to the game, players, or leaderboard, politely state: "I am the Fraud Buster Challenge AI, and my expertise is strictly limited to analyzing the game's database. Ask me about player rankings, company scores, or industry performance!"
9. Be professional, booth-friendly, and concise.

Question: {question}
""".strip()
    try:
        conn = get_active_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DBMS_CLOUD_AI.GENERATE(
                    prompt       => :prompt,
                    profile_name => 'FRAUD_BUSTER_AI',
                    action       => 'narrate'
                )
                FROM dual
                """,
                {"prompt": prompt},
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                st.session_state.select_ai_available = True
                return str(row[0]).strip()
            raise RuntimeError("Select AI returned no response.")
    except Exception as exc:
        st.session_state.select_ai_available = False
        st.session_state.db_error = f"Select AI notice: {exc}"
        raise


@st.cache_resource(show_spinner=False, ttl=1800)
def get_connection():
    """Create a cached Oracle DB connection using Streamlit secrets or environment variables."""
    if oracledb is None:
        raise RuntimeError("python-oracledb is not installed. Run: pip install oracledb")

    def cfg(name: str, default=None):
        try:
            value = st.secrets.get(name)
            if value:
                return value
        except Exception:
            pass
        return os.getenv(name, default)

    user = cfg("DB_USER", "FRAUD_USER")
    password = cfg("DB_PASSWORD")
    dsn = cfg("DB_DSN", "starkapexdb_high")
    wallet_dir = cfg("WALLET_DIR", "adb_wallet")
    wallet_password = cfg("WALLET_PASSWORD", password)

    if not password:
        raise RuntimeError("Missing DB_PASSWORD. Add it to .streamlit/secrets.toml or environment variables.")

    call_timeout = int(cfg("DB_CALL_TIMEOUT_MS", 60000))

    wallet_path = Path(wallet_dir)
    if not wallet_path.exists():
        zip_path = Path("adb_wallet.zip")
        if zip_path.exists():
            wallet_path.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(wallet_path)

    if wallet_path.exists():
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=str(wallet_path.resolve()),
            wallet_location=str(wallet_path.resolve()),
            wallet_password=wallet_password,
        )
    else:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)

    try:
        conn.call_timeout = call_timeout
    except Exception:
        pass

    return conn


def get_active_connection():
    """Returns the cached connection if active, otherwise clears cache and reconnects."""
    try:
        conn = get_connection()
        conn.ping()
        return conn
    except Exception:
        st.cache_resource.clear()
        return get_connection()


def run_query(sql: str, params: Optional[dict] = None, fetch: str = "all"):
    conn = get_active_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()
        conn.commit()
        return None


def normalize_industry_for_db(industry: str) -> List[str]:
    if industry == "Telco & Technology":
        return ["Telco & Technology", "Telco and Technology"]
    return [industry]


FALLBACK_CASES = [
    Case(1, "Banking/Finance", "Wire Transfer", "Felix Lim", ["Transfer: $70,000", "Destination: New account", "Timing: After password reset", "Device: Unknown"], True, "High-value transfer after a password reset to a new account from an unknown device."),
    Case(2, "Banking/Finance", "Savings", "Emma Tan", ["Deposits: Regular", "Withdrawals: Stable", "Channel: Same branch", "Balance: Normal"], False, "Stable behavior, known channel, and no abnormal balance movement."),
    Case(3, "Banking/Finance", "Card Usage", "David Ong", ["Spend: Sudden spike", "Location: Overseas", "Device: New", "Amount: $9,000 in 1 hr"], True, "Rapid overseas spend from a new device is a strong fraud signal."),
]


def load_cases(industry: str) -> List[Case]:
    try:
        industries = normalize_industry_for_db(industry)
        placeholders = ",".join([f":i{x}" for x in range(len(industries))])
        params = {f"i{x}": val for x, val in enumerate(industries)}
        rows = run_query(
            f"""
            SELECT case_id, industry, scenario_type, name,
                   attribute_1, attribute_2, attribute_3, attribute_4,
                   is_fraud, explanation
            FROM cases
            WHERE industry IN ({placeholders})
            ORDER BY DBMS_RANDOM.VALUE
            FETCH FIRST :limit ROWS ONLY
            """,
            {**params, "limit": CASES_PER_SESSION},
        )
        cases = [
            Case(
                case_id=int(r[0]),
                industry=r[1] or industry,
                scenario_type=r[2] or "Case",
                name=r[3] or "Subject",
                attributes=[x for x in [r[4], r[5], r[6], r[7]] if x],
                is_fraud=str(r[8]).upper() == "Y",
                explanation=r[9] or "Signals reviewed by AI risk logic.",
            )
            for r in rows
        ]
        if len(cases) >= CASES_PER_SESSION:
            st.session_state.db_error = None
            return cases
        raise RuntimeError(f"Only found {len(cases)} cases for {industry}.")
    except Exception as exc:
        st.session_state.db_error = str(exc)
        random.shuffle(FALLBACK_CASES)
        return FALLBACK_CASES[:CASES_PER_SESSION]


def create_player(name: str, company: str, industry: str) -> Optional[int]:
    try:
        conn = get_active_connection()
        with conn.cursor() as cur:
            out_id = cur.var(oracledb.NUMBER)
            cur.execute(
                """
                INSERT INTO players (name, company, industry)
                VALUES (:name, :company, :industry)
                RETURNING player_id INTO :player_id
                """,
                {"name": name, "company": company, "industry": industry, "player_id": out_id},
            )
            conn.commit()
            return int(out_id.getvalue()[0])
    except Exception as exc:
        st.session_state.db_error = str(exc)
        return None


def save_leaderboard(player_id: Optional[int], score: int, total_time: int, player_type: str = "HUMAN") -> None:
    if not player_id:
        return
    try:
        run_query(
            """
            INSERT INTO leaderboard (player_id, score, total_time, player_type, session_id)
            VALUES (:player_id, :score, :total_time, :player_type, :session_id)
            """,
            {
                "player_id": player_id,
                "score": int(score),
                "total_time": int(total_time),
                "player_type": player_type,
                "session_id": st.session_state.session_id
            },
            fetch="none",
        )
        # st.session_state.score_saved = True # Handled in submit_answers
        st.session_state.db_error = None
    except Exception as exc:
        st.session_state.db_error = f"Leaderboard save error ({player_type}): {exc}"
        raise


def save_case_results(player_id: Optional[int], result: Dict, actor_type: str = "HUMAN") -> None:
    if not player_id:
        return
    try:
        conn = get_active_connection()
        with conn.cursor() as cur:
            for case in st.session_state.cases:
                info = result["case_scores"][case.case_id]
                selected = str(info["selected"])
                selected_answer = "Y" if selected == "Fraud" else ("N" if selected == "Legit" else None)
                cur.execute(
                    """
                    INSERT INTO player_case_results (
                        player_id, case_id, selected_answer, is_correct,
                        confidence, response_time, base_score, speed_bonus,
                        confidence_bonus, total_score, actor_type
                    ) VALUES (
                        :player_id, :case_id, :selected_answer, :is_correct,
                        :confidence, :response_time, :base_score, :speed_bonus,
                        :confidence_bonus, :total_score, :actor_type
                    )
                    """,
                    {
                        "player_id": player_id,
                        "case_id": case.case_id,
                        "selected_answer": selected_answer,
                        "is_correct": "Y" if info["correct"] else "N",
                        "confidence": str(info["confidence"])[:10],
                        "response_time": int(info["answered_at"]),
                        "base_score": int(info["base"]),
                        "speed_bonus": int(info["speed"]),
                        "confidence_bonus": int(info["confidence_bonus"]),
                        "total_score": int(info["total"]),
                        "actor_type": actor_type,
                    },
                )
            conn.commit()
    except Exception as exc:
        st.session_state.db_error = str(exc)


def load_leaderboard(limit: int = 15) -> List[Tuple[str, str, int, int, str, str]]:
    try:
        rows = run_query(
            """
            SELECT p.name, p.company, h.score, NVL(h.total_time, 9999) AS total_time, p.industry,
                   CASE WHEN h.score >= NVL(a.score, 0) THEN 'YES' ELSE 'NO' END as beat_ai
            FROM leaderboard h
            JOIN players p ON p.player_id = h.player_id
            LEFT JOIN leaderboard a ON h.session_id = a.session_id AND a.player_type = 'AI'
            WHERE h.player_type = 'HUMAN'
            ORDER BY h.score DESC, NVL(h.total_time, 9999) ASC, h.created_at ASC
            FETCH FIRST :limit ROWS ONLY
            """,
            {"limit": limit},
        )
        return [(r[0] or "PLAYER", r[1] or "", int(r[2] or 0), int(r[3] or 0), r[4] or "", r[5]) for r in rows]
    except Exception:
        return [
            ("AAA", "Oracle AI", 480, 18, "Banking/Finance", "YES"),
            ("BOT", "Demo", 390, 24, "Telco & Technology", "NO"),
            ("ZEN", "Cloud", 360, 29, "Insurance", "YES"),
        ]


def load_ai_vs_humans() -> Tuple[int, int]:
    """Return (ai_wins, human_wins) comparing paired sessions.
    
    Pairs Human and AI records by session_id. 
    Falls back to benchmark comparison for unpaired/old records.
    """
    try:
        # Tally sessions where we have both Human and AI scores
        paired_wins = run_query(
            """
            SELECT
              SUM(CASE WHEN a.score > h.score THEN 1 ELSE 0 END) AS ai_wins,
              SUM(CASE WHEN h.score >= a.score THEN 1 ELSE 0 END) AS human_wins
            FROM leaderboard h
            JOIN leaderboard a ON h.session_id = a.session_id
            WHERE h.player_type = 'HUMAN' AND a.player_type = 'AI'
            """,
            fetch="one",
        )
        
        # Tally old records that don't have a paired session (benchmark-based)
        unpaired_wins = run_query(
            """
            SELECT
              SUM(CASE WHEN score < 300 THEN 1 ELSE 0 END) AS ai_wins,
              SUM(CASE WHEN score >= 300 THEN 1 ELSE 0 END) AS human_wins
            FROM leaderboard
            WHERE player_type = 'HUMAN'
              AND (session_id IS NULL OR session_id NOT IN (SELECT session_id FROM leaderboard WHERE player_type = 'AI'))
            """,
            fetch="one",
        )
        
        ai_p, human_p = int(paired_wins[0] or 0), int(paired_wins[1] or 0)
        ai_u, human_u = int(unpaired_wins[0] or 0), int(unpaired_wins[1] or 0)
        
        return (ai_p + ai_u), (human_p + human_u)
    except Exception:
        return 12, 8


def seconds_elapsed() -> int:
    if not st.session_state.start_time:
        return 0
    return min(CHALLENGE_SECONDS, int(time.time() - st.session_state.start_time))


def seconds_remaining() -> int:
    return max(0, CHALLENGE_SECONDS - seconds_elapsed())


def speed_bonus(elapsed: int) -> int:
    if elapsed < 10:
        return 50
    if elapsed < 20:
        return 30
    if elapsed < 30:
        return 10
    return 0


def score_case(case: Case) -> Dict[str, Union[int, bool, str]]:
    selected = st.session_state.answers.get(case.case_id)
    confidence = st.session_state.confidence.get(case.case_id, "Not Sure")
    answered_at = st.session_state.case_times.get(case.case_id, seconds_elapsed())
    is_answered = selected in ["Legit", "Fraud"]
    correct = is_answered and ((selected == "Fraud") == case.is_fraud)
    base = 100 if correct else 0
    speed = speed_bonus(answered_at) if is_answered and correct else 0
    conf = 30 if correct and confidence == "Confident" else (-20 if (is_answered and not correct and confidence == "Confident") else 0)
    total = base + speed + conf
    return {
        "selected": selected or "No Answer",
        "confidence": confidence,
        "correct": bool(correct),
        "base": base,
        "speed": speed,
        "confidence_bonus": conf,
        "total": total,
        "answered_at": answered_at,
    }


def calculate_ai_result() -> Dict:
    """Ask Select AI to decide on the same 3 cases to get a real AI score."""
    case_scores = {}
    prompt = (
        "Act as an expert Fraud Buster AI. Analyze these 3 cases and decide if each is 'Fraud' or 'Legit'. "
        "Also state your confidence as 'Confident' or 'Not Sure'.\n\n"
    )
    for idx, case in enumerate(st.session_state.cases, start=1):
        prompt += f"CASE {idx}: {case.industry} {case.scenario_type} for {case.name}. Signals: {', '.join(case.attributes)}\n"
    
    prompt += "\nFormat your response EXACTLY as:\nCASE 1: [Fraud/Legit], [Confident/Not Sure]\nCASE 2: ...\nCASE 3: ..."
    
    try:
        response = select_ai(prompt)
        # Parse AI response. Look for "CASE X:" pattern anywhere in the lines.
        lines = [l.strip() for l in response.split("\n") if ":" in l and "CASE" in l.upper()]
        
        for idx, case in enumerate(st.session_state.cases, start=0):
            # Default to "Legit" but try to parse
            selected = "Legit"
            confidence = "Not Sure"
            
            # Find the line corresponding to this case index if possible
            if idx < len(lines):
                try:
                    parts = lines[idx].split(":")[-1].split(",")
                    if len(parts) >= 1:
                        val = parts[0].upper()
                        if "FRAUD" in val: selected = "Fraud"
                        elif "LEGIT" in val: selected = "Legit"
                    if len(parts) >= 2:
                        conf_val = parts[1].upper()
                        if "CONFIDENT" in conf_val: confidence = "Confident"
                        elif "NOT SURE" in conf_val: confidence = "Not Sure"
                except Exception:
                    pass
            
            # AI scoring - More dynamic
            answered_at = random.randint(4, 14) 
            correct = (selected == "Fraud") == case.is_fraud
            base = 100 if correct else 0
            speed = speed_bonus(answered_at) if correct else 0
            conf_bonus = 30 if correct and confidence == "Confident" else (-20 if (not correct and confidence == "Confident") else 0)
            total = base + speed + conf_bonus
            
            case_scores[case.case_id] = {
                "selected": selected,
                "confidence": confidence,
                "correct": correct,
                "base": base,
                "speed": speed,
                "confidence_bonus": conf_bonus,
                "total": total,
                "answered_at": answered_at,
            }
    except Exception as exc:
        st.session_state.db_error = f"Select AI Case Analysis notice: {exc}. Using AI fallback scores."
        # Varied Fallback AI performance
        for case in st.session_state.cases:
            correct = random.random() > 0.1 # 90% accuracy fallback
            selected = ("Fraud" if case.is_fraud else "Legit") if correct else ("Legit" if case.is_fraud else "Fraud")
            confidence = "Confident" if random.random() > 0.2 else "Not Sure"
            answered_at = random.randint(6, 16)
            
            base = 100 if correct else 0
            speed = speed_bonus(answered_at) if correct else 0
            conf_val = 30 if correct and confidence == "Confident" else (-20 if (not correct and confidence == "Confident") else 0)
            total = base + speed + conf_val
            
            case_scores[case.case_id] = {
                "selected": selected,
                "confidence": confidence,
                "correct": correct,
                "base": base,
                "speed": speed,
                "confidence_bonus": conf_val,
                "total": total,
                "answered_at": answered_at,
            }

    total_score = sum(int(v["total"]) for v in case_scores.values())
    # Calculate a realistic total assessment time (sum of case processing + overhead)
    total_time = sum(v["answered_at"] for v in case_scores.values()) // 2 + random.randint(2, 5)
    
    return {
        "case_scores": case_scores,
        "total_score": total_score,
        "total_time": total_time,
    }


def calculate_result() -> Dict:
    case_scores = {case.case_id: score_case(case) for case in st.session_state.cases}
    total_score = sum(int(v["total"]) for v in case_scores.values())
    total_time = seconds_elapsed()
    return {
        "case_scores": case_scores,
        "total_score": total_score,
        "total_time": total_time,
    }


def css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;700;800;900&display=swap');

        :root {{
            --red: {RED};
            --amber: {AMBER};
            --cyan: {CYAN};
            --oracle: {ORACLE_RED};
        }}

        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {{
            background: #030303;
            color: white;
            font-family: 'Oracle Sans', 'Inter', system-ui, sans-serif;
        }}

        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background:
                radial-gradient(circle at 50% 0%, rgba(255,45,31,.36), transparent 35%),
                radial-gradient(circle at 12% 28%, rgba(0,229,255,.16), transparent 28%),
                radial-gradient(circle at 88% 34%, rgba(255,176,0,.13), transparent 31%),
                linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px);
            background-size: auto, auto, auto, 100% 4px;
            z-index: 0;
        }}

        .block-container {{
            max-width: 1440px;
            padding: 1.2rem 2.2rem 3rem 27.5rem;
            position: relative;
            z-index: 1;
        }}

        [data-testid="stSidebar"], header, footer, #MainMenu {{ display: none !important; }}

        .arcade-title-small {{
            color: rgba(255,255,255,.48);
            letter-spacing: .1em;
            font-weight: 900;
            font-size: 2.3rem;
        }}
        .arcade-title {{
            font-weight: 900;
            letter-spacing: -.075em;
            line-height: .88;
            font-size: clamp(3.2rem, 7vw, 7.4rem);
            margin: .2rem 0 0 0;
        }}
        .subtitle {{
            color: rgba(255,255,255,.68);
            font-weight: 800;
            font-size: 1.4rem;
            letter-spacing: .09em;
            text-transform: uppercase;
            margin-top: .8rem;
        }}

        .score-grid {{
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 1.2rem;
            align-items: center;
            margin: 1.2rem 0 1rem;
        }}
        .score-card {{
            border-radius: 2rem;
            padding: 1.3rem 1.5rem;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(255,255,255,.06);
            box-shadow: 0 0 55px rgba(0,0,0,.42);
        }}
        .score-card.ai {{
            border-color: rgba(255,45,31,.42);
            background: rgba(255,45,31,.10);
            box-shadow: 0 0 50px rgba(255,45,31,.20);
        }}
        .score-card.human {{
            border-color: rgba(0,229,255,.42);
            background: rgba(0,229,255,.10);
            text-align: right;
            box-shadow: 0 0 50px rgba(0,229,255,.15);
        }}
        .score-label {{
            font-size: 1.3rem;
            letter-spacing: .38em;
            color: rgba(255,255,255,.58);
            font-weight: 900;
            text-align: center;
        }}
        .score-number {{
            font-size: clamp(4rem, 8vw, 8.3rem);
            font-weight: 900;
            letter-spacing: -.09em;
            line-height: .8;
            text-align: center;
        }}
        .score-number.red {{ color: var(--red); }}
        .score-number.cyan {{ color: var(--cyan); }}
        .vs {{ color: rgba(255,255,255,.34); font-size: clamp(2.4rem, 5vw, 5rem); font-weight: 900; }}

        .timer-wrap {{
            border: 1px solid rgba(255,176,0,.35);
            background: rgba(255,176,0,.07);
            border-radius: 1.6rem;
            padding: .9rem 1.2rem;
            text-align: right;
        }}
        .timer-label {{ font-size: 1rem; letter-spacing: .34em; color: rgba(255,255,255,.52); font-weight: 900; }}
        .timer-number {{ font-size: 4rem; color: var(--amber); font-weight: 900; letter-spacing: -.07em; line-height: .82; }}
        .timer-bar {{
            height: .8rem;
            border-radius: 999px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,.1);
            background: rgba(255,255,255,.08);
            margin: .7rem 0 1.1rem;
        }}
        .timer-fill {{ height: 100%; border-radius: 999px; box-shadow: 0 0 25px rgba(255,45,31,.8); }}

        .left-panel {{
            position: fixed;
            left: 1.2rem;
            top: 1.2rem;
            bottom: 1.2rem;
            width: 25rem;
            border-radius: 2rem;
            border: 1px solid rgba(255,255,255,.11);
            background: rgba(255,255,255,.06);
            backdrop-filter: blur(18px);
            box-shadow: 0 0 70px rgba(0,0,0,.55);
            z-index: 999;
            padding: 1.1rem;
            overflow-y: auto;
        }}
        .left-panel-title {{ font-size: 1.5rem; letter-spacing: .1em; color: rgba(255,255,255,.44); font-weight: 900; margin-bottom: 1.5rem; text-align: center; }}
        
        .leader-card {{
            display: flex;
            align-items: center;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 1.2rem;
            padding: 0.8rem 1rem;
            margin-bottom: 0.8rem;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s ease;
        }}
        .leader-card.you {{
            background: rgba(255,45,31,0.08);
            border-color: rgba(255,45,31,0.3);
        }}
        .leader-card:hover {{ transform: translateX(5px); background: rgba(255,255,255,0.06); }}

        .beat-glow {{
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
        }}
        .beat-glow.yes {{ background: #00ff70; box-shadow: 0 0 15px #00ff70; }}
        .beat-glow.no {{ background: rgba(255,255,255,0.1); }}

        .rank-badge {{
            width: 2.2rem;
            height: 2.2rem;
            background: rgba(255,255,255,0.1);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 1rem;
            margin-right: 1rem;
            flex-shrink: 0;
            border: 1px solid rgba(255,255,255,0.1);
            color: rgba(255,255,255,0.6);
        }}
        .rank-1 .rank-badge {{ color: #ffb000; border-color: #ffb000; box-shadow: 0 0 10px rgba(255,176,0,0.3); }}
        .rank-2 .rank-badge {{ color: #e0e0e0; border-color: #e0e0e0; }}
        .rank-3 .rank-badge {{ color: #cd7f32; border-color: #cd7f32; }}

        .player-info {{ flex-grow: 1; min-width: 0; }}
        .player-name {{ font-weight: 900; font-size: 1.05rem; line-height: 1.1; color: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .company-name {{ font-size: 1rem; font-weight: 700; opacity: 0.6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 0.2rem; }}

        .stat-block {{ text-align: right; flex-shrink: 0; padding-left: 1rem; }}
        .score-val {{ font-size: 1.4rem; font-weight: 900; line-height: 1; color: white; }}
        .time-val {{ font-size: .8rem; font-weight: 500; color: rgba(255,255,255,0.4); margin-top: 0.2rem; text-transform: uppercase; }}

        .beat-tag {{
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 900;
            padding: 0.15rem 0.4rem;
            border-radius: 0.4rem;
            margin-top: 0.4rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        .beat-tag.yes {{ background: rgba(0,255,112,0.15); color: #00ff70; border: 1px solid rgba(0,255,112,0.3); }}
        .beat-tag.no {{ background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3); border: 1px solid rgba(255,255,255,0.1); }}

        .glass-card {{
            border-radius: 2rem;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(10,10,10,.72);
            box-shadow: 0 25px 70px rgba(0,0,0,.36);
            padding: 1.35rem;
        }}
        .case-card {{
            border-radius: 2rem;
            border: 1px solid rgba(255,255,255,.12);
            background: linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.03) 38%, rgba(0,0,0,.55));
            box-shadow: 0 25px 70px rgba(0,0,0,.45);
            padding: 1.1rem 1.1rem 1.25rem;
            min-height: 28rem;
            position: relative;
        }}
        .case-code {{ color: rgba(255,255,255,.42); font-weight: 900; letter-spacing:.1em; font-size:1.2rem; }}
        .case-title {{ font-size: 2rem; font-weight: 900; letter-spacing: -.055em; line-height: .95; margin-top:.42rem; }}
        .case-name {{ color: rgba(255,255,255,.58); font-weight:800; margin-top:.35rem; }}
        .risk-pill {{
            display:inline-flex;
            align-items:center;
            border: 1px solid rgba(255,176,0,.65);
            color: var(--amber);
            border-radius:999px;
            padding:.35rem .58rem;
            font-size:1rem;
            font-weight:900;
            letter-spacing:.16em;
            margin-bottom: .8rem;
        }}
        .attr-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:.55rem; margin:1rem 0; }}
        .attr {{
            border-radius: 1rem;
            border: 1px solid rgba(255,255,255,.10);
            background: rgba(255,255,255,.07);
            padding: .72rem .76rem;
            min-height: 3.7rem;
            font-size:1rem;
            font-weight:800;
            color: rgba(255,255,255,.90);
        }}

        div[data-testid="stButton"] > button {{
            width: 100%;
            border-radius: 1.2rem;
            border: 1px solid rgba(255,255,255,.16);
            background: rgba(255,255,255,.08);
            color: white;
            font-weight: 900;
            letter-spacing: .04em;
            padding: .9rem 1rem;
            transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
        }}
        div[data-testid="stButton"] > button:hover {{
            transform: scale(1.03);
            border-color: rgba(255,255,255,.38);
            color: white;
            box-shadow: 0 0 35px rgba(255,45,31,.20);
        }}
        div[data-testid="stButton"] > button:active {{ transform: scale(.98); }}

        .primary-button div[data-testid="stButton"] > button {{
            background: var(--red);
            border-color: rgba(255,45,31,.75);
            box-shadow: 0 0 55px rgba(255,45,31,.45);
            color: white;
            font-size: 2.8rem;
            padding: 1.5rem 2rem;
            min-height: 6rem;
            text-transform: uppercase;
        }}
        
        /* Selection Highlight Styles - Robust Sibling Selector */
        .element-container:has(#legit-marker),
        .element-container:has(#fraud-marker),
        .element-container:has(#inactive-marker) {{
            position: absolute;
            height: 0;
            margin: 0;
            padding: 0;
            overflow: hidden;
            visibility: hidden;
        }}

        .element-container:has(#legit-marker) + .element-container [data-testid="stButton"] button,
        .element-container:has(#fraud-marker) + .element-container [data-testid="stButton"] button {{
            background-color: var(--amber) !important;
            border-color: var(--amber) !important;
            box-shadow: 0 0 40px rgba(255, 176, 0, 0.8) !important;
            color: black !important;
            transform: scale(1.05);
        }}

        .result-score {{
            text-align: center;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(255,255,255,.05);
            border-radius: 2rem;
            padding: 2rem 1rem;
            box-shadow: 0 0 70px rgba(255,45,31,.12);
        }}
        .victory-label {{ color: rgba(255,255,255,.56); letter-spacing:.48em; font-size:1rem; font-weight:900; }}
        .player-score {{ color: var(--red); font-size: clamp(6rem, 12vw, 12rem); font-weight:900; letter-spacing:-.1em; line-height:.82; }}
        .explain-box {{
            border:1px solid rgba(255,255,255,.10);
            background:rgba(0,0,0,.35);
            border-radius:1.2rem;
            padding:1rem;
            color:rgba(255,255,255,.78);
            font-weight:500;
            font-size:1rem;
            line-height:1.55;
            overflow-wrap:anywhere;
            word-break:normal;
            white-space:normal;
        }}

        .explain-label {{
            color:rgba(255,255,255,.54);
            font-size:1rem;
            font-weight:900;
            letter-spacing:.08em;
            margin-bottom:.25rem;
            text-transform:uppercase;
        }}

        .explain-value {{
            color:rgba(255,255,255,.88);
            font-size:1rem;
            font-weight:800;
            line-height:1.45;
            margin-bottom:.8rem;
            overflow-wrap:anywhere;
        }}
        input, textarea, [data-baseweb="select"] > div {{
            background: rgba(255,255,255,.08) !important;
            color: white !important;
            border-color: rgba(255,255,255,.16) !important;
            border-radius: 1rem !important;
        }}
        label, .stRadio label, .stTextInput label {{ color: rgba(255,255,255,.78) !important; font-weight: 800 !important; }}

        /* Hide "Press enter to apply" hint */
        [data-testid="InputInstructions"] {{
            display: none !important;
        }}

        .db-warning {{
            border:1px solid rgba(255,176,0,.35);
            background:rgba(255,176,0,.08);
            color:rgba(255,255,255,.72);
            border-radius:1rem;
            padding:.8rem 1rem;
            font-size:1rem;
            margin:.8rem 0;
        }}

        @media (max-width: 980px) {{
            .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
            .left-panel {{ position: relative; width: auto; height:auto; left:auto; top:auto; bottom:auto; margin-bottom:1rem; }}
            .score-grid {{ grid-template-columns: 1fr; }}
            .vs {{ text-align:center; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


INDUSTRY_ICONS = {
    "Banking/Finance": "💰",
    "Insurance": "🛡️",
    "Telco & Technology": "📱",
    "Healthcare": "🏥",
    "Industrial": "🏗️",
    "Government": "⚖️",
}

def get_company_color(company: str) -> str:
    palette = ["#00e5ff", "#ffb000", "#ff2d1f", "#70ff00", "#ff00e5", "#ffffff", "#00ff70", "#008cff", "#ff8c00"]
    if not company: return "#ffffff"
    # Stable color based on company name hash
    idx = sum(ord(c) for c in company) % len(palette)
    return palette[idx]

def render_left_panel() -> None:
    leaderboard = load_leaderboard(limit=15)
    current_name = st.session_state.player_name.strip()

    html = [
        '<div class="left-panel">',
        '<div class="left-panel-title">LEADERBOARD</div>',
        '<div class="leader-list">'
    ]

    if not leaderboard:
        html.append('<div style="text-align:center; color:rgba(255,255,255,0.3); padding:3rem 0;">No rounds played yet</div>')
    else:
        for idx, (name, company, score, total_time, industry, beat_ai) in enumerate(leaderboard, start=1):
            is_you = current_name and name.strip().lower() == current_name.lower()
            comp_color = get_company_color(company)
            beat_class = "yes" if beat_ai == "YES" else "no"
            rank_class = f"rank-{idx}" if idx <= 3 else ""

            html.append(
                f'<div class="leader-card {"you" if is_you else ""} {rank_class}">'
                f'<div class="beat-glow {beat_class}"></div>'
                f'<div class="rank-badge">{idx}</div>'
                f'<div class="player-info">'
                f'<div class="player-name">{escape_html(name)}</div>'
                f'<div class="company-name" style="color:{comp_color};">{escape_html(company or "—")}</div>'
                f'<div class="beat-tag {beat_class}">BEAT AI: {beat_ai}</div>'
                f'</div>'
                f'<div class="stat-block">'
                f'<div class="score-val">{score}</div>'
                f'<div class="time-val">{total_time}s</div>'
                f'</div>'
                f'</div>'
            )

    html.append('</div></div>')
    st.markdown("".join(html), unsafe_allow_html=True)

def escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def clean_ai_text(value: str) -> str:
    text = str(value or "")
    replacements = {
        "**": "",
        "__": "",
        "###": "",
        "##": "",
        "#": "",
        "* ": "",
        "\r": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split())

def short_name(name: str) -> str:
    parts = [p for p in name.upper().split() if p]
    if not parts:
        return "PLAYER"
    if len(parts) == 1:
        return parts[0][:10]
    return f"{parts[0][:1]} {parts[-1][:9]}"


def render_header(show_timer: bool = False) -> None:
    ai_wins, human_wins = load_ai_vs_humans()
    remaining = seconds_remaining() if st.session_state.page == "cases" else CHALLENGE_SECONDS
    fill = int((remaining / CHALLENGE_SECONDS) * 100)
    fill_color = AMBER if remaining <= 10 else RED

    top_right = ""
    if show_timer:
        top_right = f"""
        <div class="timer-wrap">
          <div class="timer-label">TIME</div>
          <div class="timer-number">{remaining:02d}</div>
        </div>
        """

    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;gap:2rem;align-items:flex-end;">
          <div>
            <div class="arcade-title-small">FRAUD BUSTER CHALLENGE</div>
            <div class="arcade-title">BEAT  THE  AI</div>
            <div class="subtitle">{APP_SUBTITLE}</div>
          </div>
          {top_right}
        </div>
        <div class="score-grid">
          <div class="score-card human">
            <div class="score-label">HUMAN WINS</div>
            <div class="score-number cyan">{human_wins}</div>
          </div>
          <div class="vs">VS</div>
          <div class="score-card ai">
            <div class="score-label">AI WINS</div>
            <div class="score-number red">{ai_wins}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if show_timer:
        st.markdown(
            f"""
            <div class="timer-bar"><div class="timer-fill" style="width:{fill}%;background:{fill_color};"></div></div>
            """,
            unsafe_allow_html=True,
        )


def render_landing() -> None:
    render_header(show_timer=False)
    if st.session_state.db_error:
        st.markdown(f'<div class="db-warning">Database notice: {escape_html(st.session_state.db_error)}</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.markdown(
            """
            <div class="glass-card" style="min-height: 20rem;">
              <div class="case-code">FRAUD or LEGIT - Decide Fast</div>
              <div class="case-title" style="font-size:3.2rem;">3 CASES. 60 SECONDS.<br> ONE CHALLENGE.</div>
              <p style="color:rgba(255,255,255,.68);font-weight:500;font-size:1.2rem;line-height:1.55;">
                Every second counts. Every call matters. Outplay the AI to secure the win for Humans.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        st.markdown('<div class="primary-button" style="margin-top:2rem;">', unsafe_allow_html=True)
        if st.button("START CHALLENGE", use_container_width=True):
            st.session_state.page = "registration"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        # AI response window on top - min-height matched to c1 card
#        display_text = clean_ai_text(st.session_state.event_answer) if st.session_state.event_answer else "SELECT AI can provide information from the game database. Ask questions like 'Who is the top player today?' or 'Which company has the highest score?'. The AI's answers will be based on the game data and may not always be perfect."
        display_text = clean_ai_text(st.session_state.event_answer) if st.session_state.event_answer else (
            "Use SELECT AI to explore game data.\n\n\n"
            "Try questions like:\n"
            "* ""Who is the top player today?""\n"
            "* ""Which company has the highest score?""\n\n"
            "The AI's answers will be based on the game data and may not always be perfect."
        )
        text_opacity = "1" if st.session_state.event_answer else "0.4"
        
        st.markdown(
            f'<div class="explain-box" style="margin-bottom:1rem; min-height: 14.5rem; color:rgba(255,255,255,{text_opacity});">'
            f'{escape_html(display_text)}'
            '</div>', 
            unsafe_allow_html=True
        )

        # Header right above the input
        st.markdown('<div class="case-code">ASK SELECT AI</div>', unsafe_allow_html=True)
        
        # Checking for Enter press via on_change or simply checking the value change
        question = st.text_input(
            "Query the game database",
            key="event_question_input",
            placeholder="e.g., Who is the top player today?",
            label_visibility="collapsed"
        )
        
        # If user pressed enter, question is in session state
        if question and st.session_state.event_question_input != st.session_state.get("last_asked"):
            with st.spinner("Select AI is querying the game database..."):
                st.session_state.event_answer = answer_event_question(question.strip())
                st.session_state.last_asked = question
                st.rerun()

        st.markdown('<div style="margin-top:0.8rem;">', unsafe_allow_html=True)
        if st.button("ASK AI", use_container_width=True):
            if question.strip():
                with st.spinner("Select AI is querying the game database..."):
                    st.session_state.event_answer = answer_event_question(question.strip())
                    st.session_state.last_asked = question
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


def render_case_card(case: Case, index: int) -> None:
    score_info = score_case(case)
    selected = st.session_state.answers.get(case.case_id)
    risk = "CRITICAL" if any("unknown" in a.lower() or "foreign" in a.lower() or "spike" in a.lower() or "duplicate" in a.lower() for a in case.attributes) else "REVIEW"
    attrs_to_show = case.attributes[:1]
    attrs_html = "".join(f'<div class="attr">{escape_html(a)}</div>' for a in attrs_to_show)
    st.markdown(
        f"""
        <div class="case-card">
          <div class="risk-pill">{risk}</div>
          <div class="case-code">CASE {index:02d}</div>
          <div class="case-title">{escape_html(case.scenario_type.upper())}</div>
          <div class="case-name">{escape_html(case.name)} · {escape_html(case.industry)}</div>
          <div class="attr-grid">{attrs_html}</div>
          <div style="height:.45rem"></div>
        """,
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns(2)
    with b1:
        is_legit = (selected == "Legit")
        st.markdown(f'<div id="{"legit-marker" if is_legit else "inactive-marker"}"></div>', unsafe_allow_html=True)
        if st.button("LEGIT", key=f"legit_btn_{case.case_id}", use_container_width=True):
            st.session_state.answers[case.case_id] = "Legit"
            st.session_state.case_times[case.case_id] = seconds_elapsed()
            st.rerun()
            
    with b2:
        is_fraud = (selected == "Fraud")
        st.markdown(f'<div id="{"fraud-marker" if is_fraud else "inactive-marker"}"></div>', unsafe_allow_html=True)
        if st.button("FRAUD", key=f"fraud_btn_{case.case_id}", use_container_width=True):
            st.session_state.answers[case.case_id] = "Fraud"
            st.session_state.case_times[case.case_id] = seconds_elapsed()
            st.rerun()

    st.radio(
        "Confidence",
        ["Confident", "Not Sure"],
        key=f"confidence_radio_{case.case_id}",
        horizontal=True,
        index=0 if st.session_state.confidence.get(case.case_id) == "Confident" else 1,
    )
    st.session_state.confidence[case.case_id] = st.session_state[f"confidence_radio_{case.case_id}"]
    st.markdown(
        f"""
          <div style="margin-top:.6rem;color:rgba(255,255,255,.52);font-size:1rem;font-weight:800;">
            Selected: {escape_html(score_info['selected'])} · Answered at: {score_info['answered_at']}s
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def submit_answers() -> None:
    st.session_state.submitted = True
    st.session_state.result = calculate_result()
    st.session_state.ai_result = calculate_ai_result()
    
    # Human wins if they meet or beat the AI's actual score for this session
    st.session_state.result["human_won"] = st.session_state.result["total_score"] >= st.session_state.ai_result["total_score"]
    
    if not st.session_state.score_saved:
        try:
            # Save Human results
            save_case_results(st.session_state.player_id, st.session_state.result, actor_type="HUMAN")
            save_leaderboard(
                st.session_state.player_id,
                int(st.session_state.result["total_score"]),
                int(st.session_state.result["total_time"]),
                player_type="HUMAN"
            )
            # Save AI results for the same player/session
            save_case_results(st.session_state.player_id, st.session_state.ai_result, actor_type="AI")
            save_leaderboard(
                st.session_state.player_id,
                int(st.session_state.ai_result["total_score"]),
                int(st.session_state.ai_result["total_time"]),
                player_type="AI"
            )
            st.session_state.score_saved = True
            st.session_state.db_error = None
        except Exception as exc:
            st.session_state.db_error = f"Final save failed: {exc}"
            
    st.session_state.page = "results"


@st.fragment(run_every=1.0)
def timer_fragment():
    if st.session_state.page == "cases" and not st.session_state.submitted:
        remaining = seconds_remaining()
        fill = int((remaining / CHALLENGE_SECONDS) * 100)
        fill_color = AMBER if remaining <= 10 else RED
        st.markdown(
            f"""
            <div class="timer-bar"><div class="timer-fill" style="width:{fill}%;background:{fill_color};"></div></div>
            <div style="text-align:right; font-weight:900; color:{fill_color}; font-size: 1.2rem;">{remaining}s REMAINING</div>
            """,
            unsafe_allow_html=True,
        )
        if remaining <= 0:
            st.session_state.force_submit = True
            st.rerun()

def render_cases() -> None:
    # Check for timeout or forced submission
    if (seconds_remaining() <= 0 or st.session_state.get("force_submit")) and not st.session_state.submitted:
        submit_answers()
        st.rerun()

    render_header(show_timer=False)
    st.markdown(
        f"<div class='subtitle'>Player: {escape_html(st.session_state.player_name)} · Industry: {escape_html(st.session_state.industry)}</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.db_error:
        st.markdown(f'<div class="db-warning">Database notice: {escape_html(st.session_state.db_error)} Using fallback/demo behavior where needed.</div>', unsafe_allow_html=True)

    # Isolated timer fragment that updates every second
    timer_fragment()
    
    @st.fragment
    def cases_fragment():
        cols = st.columns(3)
        for idx, case in enumerate(st.session_state.cases, start=1):
            with cols[idx - 1]:
                render_case_card(case, idx)
    
    cases_fragment()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="primary-button">', unsafe_allow_html=True)
    if st.button("LOCK IN ANSWERS", use_container_width=True):
        with st.spinner("Analyzing decisions and calculating results..."):
            submit_answers()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def render_results() -> None:
    if st.session_state.result is None:
        st.session_state.result = calculate_result()
    if st.session_state.ai_result is None:
        st.session_state.ai_result = calculate_ai_result()

    result = st.session_state.result
    ai_result = st.session_state.ai_result
    render_header(show_timer=False)
    
    # Ensure player_name is available for display
    player_display_name = st.session_state.get("player_name", "PLAYER")
    if not player_display_name or not str(player_display_name).strip():
        player_display_name = "YOU"

    verdict = "YOU WON!" if result["human_won"] else "AI WON!"
    st.markdown(
        f"""
        <div class="result-score">
          <div class="victory-label" style="font-size: 3.5rem; margin-bottom: 1.5rem; line-height: 1; font-weight: 900;">{verdict}</div>
          <div style="display: flex; justify-content: center; gap: 4rem; align-items: center; flex-wrap: wrap;">
            <div>
              <div class="player-score" style="color: var(--cyan);">{int(result['total_score'])}</div>
              <div style="font-weight:900;font-size:1.4rem; color: var(--cyan); letter-spacing: 0.1em;">{escape_html(player_display_name).upper()}</div>
              <div style="font-weight:700;font-size:0.9rem; color: rgba(255,255,255,0.4);">Assessment Speed: {int(result['total_time'])}s</div>
            </div>
            <div style="font-size: 3rem; font-weight: 900; color: rgba(255,255,255,0.2);">VS</div>
            <div>
              <div class="player-score" style="color: var(--red);">{int(ai_result['total_score'])}</div>
              <div style="font-weight:900;font-size:1.4rem; color: var(--red); letter-spacing: 0.1em;">AI</div>
              <div style="font-weight:700;font-size:0.9rem; color: rgba(255,255,255,0.4);">Assessment Speed: {int(ai_result['total_time'])}s</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state.performance_summary:
        st.markdown(
            f'<div class="explain-box">{escape_html(clean_ai_text(st.session_state.performance_summary))}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="primary-button">', unsafe_allow_html=True)
        if st.button("GENERATE SELECT AI PERFORMANCE SUMMARY", key="generate_performance_summary", use_container_width=True):
            with st.spinner("Oracle Autonomous Database is analyzing your overall performance..."):
                summary = get_performance_summary(result)
            st.session_state.performance_summary = summary
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    cols = st.columns(3)
    for idx, case in enumerate(st.session_state.cases, start=1):
        info = result["case_scores"][case.case_id]
        ai_info = ai_result["case_scores"][case.case_id]
        with cols[idx - 1]:
            st.markdown(
                f"""
                <div class="case-card" style="min-height:unset;">
                  <div class="case-code">CASE {idx:02d}</div>
                  <div class="case-title">{escape_html(case.scenario_type.upper())}</div>
                  <div class="case-name">You: {escape_html(info['selected'])} · AI: {escape_html(ai_info['selected'])}</div>
                  <div class="case-name" style="color:rgba(255,255,255,.4); font-size:0.9rem;">Correct: {'FRAUD' if case.is_fraud else 'LEGIT'}</div>
                  <div style="font-size:3.8rem;font-weight:900;letter-spacing:-.08em;color:{CYAN if info['correct'] else RED};line-height:.9;margin:1rem 0;">{int(info['total']):+d}</div>
                  <div style="color:rgba(255,255,255,.58);font-weight:800;">
                    Base {info['base']} · Speed {info['speed']} · Confidence {info['confidence_bonus']}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.session_state.case_explanations.get(case.case_id):
                explanation = st.session_state.case_explanations[case.case_id]
                st.markdown(
                    f"""
                    <div class="explain-box">
                    <div class="explain-label">Decision</div>
                    <div class="explain-value">{'Fraud' if case.is_fraud else 'Legit'}</div>
                    <div class="explain-label">Main signal</div>
                    <div class="explain-value">{escape_html(case.attributes[0] if case.attributes else case.scenario_type)}</div>
                    <div class="explain-label">AI explanation</div>
                    <div class="explain-value">{escape_html(clean_ai_text(explanation))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                if st.button("Generate AI Explanation", key=f"gen_ex_{case.case_id}", use_container_width=True):
                    with st.spinner(f"Analyzing Case {idx:02d} risk signals..."):
                        get_case_ai_explanation(case, info)
                    st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("RESET GAME", use_container_width=True):
        st.session_state.clear()
        st.rerun()


def render_registration() -> None:
    render_header(show_timer=False)
    
    # Outer centering container
    st.markdown('<div style="max-width:450px; margin: 0 auto;">', unsafe_allow_html=True)
    
    with st.container():
        st.markdown(
            """
            <div class="glass-card">
                <div class="case-code">PLAYER REGISTRATION</div>
                <div class="case-title" style="font-size:2rem;">TELL US WHO YOU ARE</div>
                <p style="color:rgba(255,255,255,.6); font-weight:700; margin-bottom:1.5rem; font-size:0.9rem;">
                    Your details will be used for the Live Leaderboard.
                </p>
            """,
            unsafe_allow_html=True
        )
        
        st.text_input("Full Name", key="player_name", placeholder="e.g., Juan Dela Cruz")
        st.text_input("Company", key="company", placeholder="e.g., Oracle")
        st.radio("Industry", INDUSTRIES, key="industry", horizontal=False) # Vertical for better fit in narrow box
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown('<div class="primary-button">', unsafe_allow_html=True)
        if st.button("BEGIN GAME", use_container_width=True):
            if not st.session_state.player_name.strip() or not st.session_state.company.strip():
                st.error("Enter full name and company to start.")
            else:
                with st.spinner("Preparing your fraud cases..."):
                    st.session_state.player_id = create_player(
                        st.session_state.player_name.strip(),
                        st.session_state.company.strip(),
                        st.session_state.industry,
                    )
                    st.session_state.session_id = uuid.uuid4().hex[:16]
                    st.session_state.cases = load_cases(st.session_state.industry)
                    st.session_state.answers = {}
                    st.session_state.confidence = {}
                    st.session_state.case_times = {}
                    st.session_state.start_time = time.time()
                    st.session_state.submitted = False
                    st.session_state.score_saved = False
                    st.session_state.result = None
                    st.session_state.page = "cases"
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div style="margin-top:0.8rem;">', unsafe_allow_html=True)
        if st.button("CANCEL", use_container_width=True):
            st.session_state.page = "landing"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True) # Close glass-card
    
    st.markdown('</div>', unsafe_allow_html=True) # Close centering div


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="shield", layout="wide", initial_sidebar_state="collapsed")
    init_state()
    css()
    render_left_panel()

    page = st.session_state.page
    if page == "landing":
        render_landing()
    elif page == "registration":
        render_registration()
    elif page == "cases":
        render_cases()
    elif page == "results":
        render_results()
    else:
        st.session_state.page = "landing"
        st.rerun()


if __name__ == "__main__":
    main()
