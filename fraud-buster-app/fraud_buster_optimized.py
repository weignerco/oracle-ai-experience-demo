import os
import random
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import streamlit as st

try:
    import oracledb
except ImportError:
    oracledb = None

# ==========================================================
# CONSTANTS & CONFIGURATION
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

# UI Colors
RED = "#ff2d1f"
AMBER = "#ffb000"
CYAN = "#00e5ff"
ORACLE_RED = "#c74634"

# Game Rules
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

# ==========================================================
# DATABASE LAYER
# ==========================================================

@st.cache_resource(show_spinner=False, ttl=1800)
def get_connection():
    """Create a cached Oracle DB connection."""
    if oracledb is None:
        raise RuntimeError("python-oracledb is not installed.")

    def cfg(name: str, default=None):
        return st.secrets.get(name) or os.getenv(name, default)

    user = cfg("DB_USER", "FRAUD_USER")
    password = cfg("DB_PASSWORD")
    dsn = cfg("DB_DSN", "starkapexdb_high")
    wallet_dir = cfg("WALLET_DIR", "adb_wallet")
    wallet_password = cfg("WALLET_PASSWORD", password)

    if not password:
        raise RuntimeError("Missing DB_PASSWORD.")

    wallet_path = Path(wallet_dir)
    if not wallet_path.exists():
        zip_path = Path("adb_wallet.zip")
        if zip_path.exists():
            wallet_path.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(wallet_path)

    try:
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
        return conn
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

def get_active_connection():
    """Returns the cached connection if active, otherwise reconnects."""
    conn = get_connection()
    if conn:
        try:
            conn.ping()
            return conn
        except Exception:
            st.cache_resource.clear()
            return get_connection()
    return None

def run_query(sql: str, params: Optional[dict] = None, fetch: str = "all"):
    """Generic query runner with robust connection handling."""
    conn = get_active_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            conn.commit()
            return True
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return None

# ==========================================================
# AI LAYER (SELECT AI)
# ==========================================================

def select_ai_call(prompt: str, action: str = "chat") -> str:
    """Encapsulated Oracle Select AI call."""
    try:
        conn = get_active_connection()
        if not conn: return ""
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
            return str(row[0]).strip() if row and row[0] else ""
    except Exception as e:
        st.session_state.db_error = f"Select AI Error: {e}"
        return ""

# ==========================================================
# STATE MANAGEMENT
# ==========================================================

def init_state():
    """Initialize all session state variables."""
    if "page" not in st.session_state:
        st.session_state.update({
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
            "event_answer": "",
            "case_explanations": {},
            "performance_summary": "",
            "db_error": None
        })

# ==========================================================
# UI COMPONENTS
# ==========================================================

def apply_custom_css():
    """Inject optimized CSS."""
    st.markdown(f"""
        <style>
        /* Base Styles */
        [data-testid="stAppViewContainer"] {{ background: #030303; color: white; }}
        .block-container {{ max-width: 1440px; padding: 2rem 2rem 2rem 27rem; }}
        
        /* Titles */
        .arcade-title {{ font-weight: 900; font-size: 5rem; line-height: 0.9; margin: 0; color: white; }}
        .subtitle {{ color: rgba(255,255,255,0.6); font-weight: 800; font-size: 1.2rem; text-transform: uppercase; }}

        /* Left Panel (Leaderboard) */
        .left-panel {{
            position: fixed; left: 1rem; top: 1rem; bottom: 1rem; width: 25rem;
            background: rgba(255,255,255,0.05); backdrop-filter: blur(15px);
            border-radius: 1.5rem; padding: 1.5rem; border: 1px solid rgba(255,255,255,0.1);
            overflow-y: auto; z-index: 1000;
        }}

        /* Cards */
        .glass-card, .case-card {{
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 1.5rem; padding: 1.5rem; margin-bottom: 1rem;
        }}
        
        /* Score Components */
        .score-grid {{ display: flex; justify-content: space-between; align-items: center; margin: 2rem 0; }}
        .score-card {{ flex: 1; padding: 1.5rem; border-radius: 1rem; text-align: center; background: rgba(255,255,255,0.03); }}
        .score-card.human {{ border: 1px solid {CYAN}; background: rgba(0,229,255,0.1); }}
        .score-card.ai {{ border: 1px solid {RED}; background: rgba(255,45,31,0.1); }}
        .score-number {{ font-size: 4rem; font-weight: 900; line-height: 1; }}

        /* Buttons */
        div[data-testid="stButton"] > button {{
            width: 100%; border-radius: 1rem; font-weight: 800;
            padding: 0.75rem; transition: all 0.2s;
        }}
        .primary-button button {{ background: {RED} !important; font-size: 1.5rem !important; height: 4rem; }}
        </style>
    """, unsafe_allow_html=True)

# ==========================================================
# PAGE ROUTING
# ==========================================================

def render_landing():
    st.markdown('<div class="arcade-title">BEAT THE AI</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subtitle">{APP_SUBTITLE}</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.markdown("""
            <div class="glass-card">
                <h3>The Challenge</h3>
                <p>3 Cases. 60 Seconds. Can your human intuition outperform Oracle Select AI?</p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("START CHALLENGE", type="primary"):
            st.session_state.page = "registration"
            st.rerun()

def render_registration():
    st.markdown("### Player Registration")
    with st.form("reg_form"):
        name = st.text_input("Name")
        company = st.text_input("Company")
        industry = st.selectbox("Industry", INDUSTRIES)
        if st.form_submit_button("BEGIN"):
            if name and company:
                st.session_state.update({
                    "player_name": name,
                    "company": company,
                    "industry": industry,
                    "page": "cases",
                    "start_time": time.time()
                })
                # In a real app, we'd load cases from DB here
                st.session_state.cases = [
                    Case(1, "Banking", "Wire Transfer", "John Doe", ["Large amount", "New device"], True, "Classic takeover"),
                    Case(2, "Insurance", "Claim", "Jane Smith", ["Recent policy", "Staged photo"], True, "Fraudulent claim"),
                    Case(3, "Retail", "Return", "Bob Ross", ["No receipt", "Multiple stores"], False, "Legit return")
                ]
                st.rerun()

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🛡️", layout="wide")
    init_state()
    apply_custom_css()
    
    # Static Sidebar for Leaderboard (Mocked for Optimization Demo)
    with st.container():
        st.markdown('<div class="left-panel"><h3>LEADERBOARD</h3><p>Ranking Top Humans...</p></div>', unsafe_allow_html=True)

    if st.session_state.page == "landing":
        render_landing()
    elif st.session_state.page == "registration":
        render_registration()
    elif st.session_state.page == "cases":
        st.write("Game cases would render here...")
        if st.button("Finish Demo"):
            st.session_state.page = "landing"
            st.rerun()

if __name__ == "__main__":
    main()
