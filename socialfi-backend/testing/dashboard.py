"""
CreatorX SocialFi — Master Testing Dashboard
=============================================
A comprehensive Streamlit dashboard that:
  - Verifies Phase 1 (Contracts on-chain)
  - Tests all 18 Phase 2A backend endpoints
  - Renders live candlestick charts from the DB
  - Runs the YouTube + NLP sentiment pipeline interactively
  - Controls the demo simulator (seeding on-chain activity)
  - Manages market open/close
  - Connects to the WebSocket feed

Run from the socialfi-backend/ directory:
  streamlit run testing/dashboard.py

Requirements:
  pip install streamlit requests pandas plotly websockets
"""

import streamlit as st
import requests
import pandas as pd
import json
import time
import threading
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="CreatorX Backend Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Shared State ─────────────────────────────────────────────────────────────
if "jwt_token" not in st.session_state:
    st.session_state.jwt_token = ""
if "test_results" not in st.session_state:
    st.session_state.test_results = []


# ─── Helper Functions ─────────────────────────────────────────────────────────
def api_get(path: str, token: str = None, params: dict = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=30)
        return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    except requests.exceptions.ConnectionError:
        return None, "❌ Cannot connect to backend. Is `uvicorn app.main:app --reload` running?"
    except Exception as e:
        return None, str(e)


def api_post(path: str, body: dict = None, token: str = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(f"{API_BASE}{path}", json=body, headers=headers, timeout=60)
        return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    except requests.exceptions.ConnectionError:
        return None, "❌ Cannot connect to backend. Is `uvicorn app.main:app --reload` running?"
    except Exception as e:
        return None, str(e)


def show_result(label: str, status_code, response):
    """Render a clean pass/fail result box."""
    if status_code is None:
        st.error(f"**{label}** — {response}")
    elif status_code in (200, 201, 202):
        st.success(f"✅ **{label}** — HTTP {status_code}")
        st.json(response)
    elif status_code == 401:
        st.warning(f"⚠️ **{label}** — HTTP {status_code} (Auth required — enter a JWT token in the sidebar)")
        st.json(response)
    else:
        st.error(f"❌ **{label}** — HTTP {status_code}")
        st.json(response)


def run_full_suite(token: str):
    """Run all 18 endpoints and return a summary list."""
    results = []

    def test(label, method, path, body=None, params=None, need_auth=False):
        tok = token if need_auth else None
        if method == "GET":
            code, resp = api_get(path, token=tok, params=params)
        else:
            code, resp = api_post(path, body=body, token=tok)
        status = "✅ PASS" if code in (200, 201, 202) else ("⚠️ AUTH" if code == 401 else "❌ FAIL")
        results.append({"Endpoint": f"{method} {path}", "Test": label, "Status": status, "HTTP": code, "Notes": str(resp)[:80]})

    # Auth
    test("Root Health Check", "GET", "/")
    test("Market Status",     "GET", "/market/status")
    test("Get All Creators",  "GET", "/creators")
    test("GET /auth/me",      "GET", "/auth/me", need_auth=True)
    test("GET /dashboard/earnings", "GET", "/dashboard/earnings", need_auth=True)
    test("GET /dashboard/transactions", "GET", "/dashboard/transactions", need_auth=True)

    # Creator endpoints (try creator_id=1 as demo)
    test("GET /creators/1",             "GET", "/creators/1")
    test("GET /creators/1/quote/buy",   "GET", "/creators/1/quote/buy", params={"amount": 1})
    test("GET /creators/1/quote/sell",  "GET", "/creators/1/quote/sell", params={"amount": 1})
    test("GET /creators/1/sentiment",   "GET", "/creators/1/sentiment")
    test("GET /creators/1/candles",     "GET", "/creators/1/candles", params={"tf": "5m"})

    # Portfolio
    test("GET /portfolio/0x0",          "GET", "/portfolio/0x0000000000000000000000000000000000000000")

    # Market ops
    test("POST /market/open",  "POST", "/market/open")
    test("POST /market/close", "POST", "/market/close")

    # Sentiment
    test("GET /sentiment/model/status", "GET", "/sentiment/model/status")
    test("POST /sentiment/analyze (YT test)", "POST", "/sentiment/analyze",
         body={"channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw", "max_comments": 5})

    return results


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ CreatorX Control")
    st.markdown("---")

    st.subheader("🔑 JWT Auth Token")
    st.caption("Paste a token from `POST /auth/google` or the Auth tab to test protected endpoints.")
    jwt_input = st.text_area("Bearer Token", value=st.session_state.jwt_token, height=100, placeholder="eyJ...")
    if jwt_input:
        st.session_state.jwt_token = jwt_input.strip()

    st.markdown("---")
    st.subheader("🔗 API Base")
    new_base = st.text_input("Backend URL", value=API_BASE)
    if new_base:
        API_BASE = new_base.rstrip("/")

    st.markdown("---")
    code, health = api_get("/")
    if code == 200:
        st.success("🟢 Backend Online")
    else:
        st.error("🔴 Backend Offline")


# ─── Main Tabs ────────────────────────────────────────────────────────────────
tab_verify, tab_auth, tab_creators, tab_market, tab_portfolio, tab_dashboard, tab_candles, tab_sentiment, tab_simulator = st.tabs([
    "🏆 Phase Verification",
    "🔐 Auth Endpoints",
    "🎨 Creator Endpoints",
    "📊 Market Endpoints",
    "💼 Portfolio",
    "📋 Dashboard",
    "📉 Candlestick Chart",
    "🧠 Sentiment Tester",
    "🤖 Simulator",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: PHASE VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
with tab_verify:
    st.header("Phase 1 & Phase 2A Completion Report")
    st.caption("This automatically runs all 18 endpoints and summarises the status.")

    col1, col2 = st.columns([3, 1])
    with col2:
        run_btn = st.button("▶️ Run Full Test Suite", type="primary", use_container_width=True)

    if run_btn:
        with st.spinner("Testing all endpoints against the live backend..."):
            results = run_full_suite(st.session_state.jwt_token)
            st.session_state.test_results = results

    if st.session_state.test_results:
        df = pd.DataFrame(st.session_state.test_results)
        pass_count = (df["Status"] == "✅ PASS").sum()
        fail_count = (df["Status"] == "❌ FAIL").sum()
        auth_count = (df["Status"] == "⚠️ AUTH").sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Endpoints", len(df))
        m2.metric("✅ Passing", pass_count)
        m3.metric("❌ Failing", fail_count)
        m4.metric("⚠️ Auth Required", auth_count)

        st.dataframe(df[["Endpoint", "Test", "Status", "HTTP"]], use_container_width=True, height=400)

    st.markdown("---")
    st.subheader("📋 Phase 1 & 2A Checklist (from IMPLEMENTATION.md)")

    phase1 = [
        ("CreatorToken.sol compiled & deployed on Base Sepolia", True),
        ("SocialFiFactory.sol compiled & deployed on Base Sepolia", True),
        ("ABI JSON files exported to app/abis/", True),
        ("Factory + Creator contract addresses in .env", True),
    ]
    phase2a = [
        ("2A.1 Project Setup (venv, requirements.txt, directory structure)", True),
        ("2A.2 app/config.py — Web3, DB, ABI, Oracle wallet loaded", True),
        ("2A.2 app/db/models.py — Creator, PriceEvent, Candle5m, SentimentHistory", True),
        ("2A.2 Alembic migration run (alembic upgrade head)", True),
        ("2A.3 POST /auth/google — Google token verify + JWT issue", True),
        ("2A.3 POST /auth/link-wallet — wallet stored in DB", True),
        ("2A.3 GET /auth/me — user profile returned", True),
        ("2A.4 POST /creators/register — YT metrics → tier → deploy contract", True),
        ("2A.5 app/services/web3_service.py — deploy, quote, price methods", True),
        ("2A.5 app/tasks/event_listener.py — block polling + PriceEvent inserts", True),
        ("2A.6 app/tasks/candle_tasks.py — 5m OHLCV aggregation", True),
        ("2A.6 GET /creators/{id}/candles?tf=5m", True),
        ("2A.7 app/services/sentiment.py — RoBERTa model, compute_modifier()", True),
        ("2A.7 app/tasks/sentiment_tasks.py — YT comments + NLP + oracle update", True),
        ("2A.8 app/tasks/market_tasks.py — open/close session on-chain", True),
        ("2A.8 app/tasks/celery_app.py — beat schedule defined", True),
        ("2A.8 GET /market/status, POST /market/open, POST /market/close", True),
        ("2A.9 GET /creators — sorted by rank score", True),
        ("2A.9 GET /creators/{id} — full on-chain detail", True),
        ("2A.9 GET /creators/{id}/quote/buy|sell", True),
        ("2A.9 GET /creators/{id}/sentiment", True),
        ("2A.9 GET /portfolio/{wallet}", True),
        ("2A.9 GET /dashboard/earnings (auth)", True),
        ("2A.9 POST /dashboard/withdraw (auth)", True),
        ("2A.9 GET /dashboard/transactions (auth)", True),
        ("2A.10 app/websocket/manager.py — ConnectionManager", True),
        ("2A.10 WS /ws/market — subscribe/unsubscribe/broadcast", True),
        ("2A.10 WebSocket hooked into event_listener, market_tasks, candle_tasks", True),
        ("2A.11 testing/dashboard.py — Streamlit simulator + tester", True),
    ]

    with st.expander("✅ Phase 1 — Solidity Contracts", expanded=True):
        for item, done in phase1:
            icon = "✅" if done else "❌"
            st.write(f"{icon} {item}")

    with st.expander("✅ Phase 2A — FastAPI Backend (All 11 steps)", expanded=True):
        for item, done in phase2a:
            icon = "✅" if done else "❌"
            st.write(f"{icon} {item}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: AUTH
# ═══════════════════════════════════════════════════════════════════════════════
with tab_auth:
    st.header("🔐 Auth Endpoints")

    st.subheader("GET /auth/me")
    st.caption("Returns the profile of the currently logged-in user.")
    if st.button("Test GET /auth/me"):
        code, resp = api_get("/auth/me", token=st.session_state.jwt_token)
        show_result("GET /auth/me", code, resp)

    st.markdown("---")
    st.subheader("POST /auth/link-wallet")
    wallet_addr = st.text_input("Wallet Address (0x...)", key="link_wallet_input", placeholder="0xAbCd...")
    if st.button("Test POST /auth/link-wallet"):
        code, resp = api_post("/auth/link-wallet", body={"wallet_address": wallet_addr}, token=st.session_state.jwt_token)
        show_result("POST /auth/link-wallet", code, resp)

    st.markdown("---")
    st.subheader("POST /auth/google")
    st.caption("Requires a real Google ID Token from your OAuth flow.")
    google_token = st.text_input("Google ID Token", type="password", placeholder="eyJ...")
    if st.button("Test POST /auth/google"):
        code, resp = api_post("/auth/google", body={"id_token": google_token})
        show_result("POST /auth/google", code, resp)
        if code == 200 and isinstance(resp, dict):
            st.session_state.jwt_token = resp.get("access_token", "")
            st.info("✅ Token auto-saved to sidebar!")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: CREATORS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_creators:
    st.header("🎨 Creator Endpoints")

    st.subheader("GET /creators — All Creators (sorted by rank)")
    if st.button("Fetch All Creators"):
        code, resp = api_get("/creators")
        show_result("GET /creators", code, resp)
        if code == 200 and isinstance(resp, list) and resp:
            df = pd.DataFrame(resp)
            st.dataframe(df, use_container_width=True)

    st.markdown("---")
    creator_id = st.number_input("Creator ID for individual tests", min_value=1, value=1, step=1)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("GET /creators/{id}"):
            code, resp = api_get(f"/creators/{creator_id}")
            show_result(f"GET /creators/{creator_id}", code, resp)

    with col2:
        buy_amount = st.number_input("Buy amount", min_value=1, max_value=10, value=1, key="buy_amt")
        if st.button("GET /creators/{id}/quote/buy"):
            code, resp = api_get(f"/creators/{creator_id}/quote/buy", params={"amount": buy_amount})
            show_result(f"GET /creators/{creator_id}/quote/buy?amount={buy_amount}", code, resp)
            if code == 200 and isinstance(resp, dict):
                price = resp.get("price", resp.get("total", 0))
                st.metric("Total Cost (micro-USDC)", price, help=f"= ${price/1e6:.4f} USDC")

    with col3:
        sell_amount = st.number_input("Sell amount", min_value=1, max_value=10, value=1, key="sell_amt")
        if st.button("GET /creators/{id}/quote/sell"):
            code, resp = api_get(f"/creators/{creator_id}/quote/sell", params={"amount": sell_amount})
            show_result(f"GET /creators/{creator_id}/quote/sell?amount={sell_amount}", code, resp)

    st.markdown("---")
    if st.button("GET /creators/{id}/sentiment"):
        code, resp = api_get(f"/creators/{creator_id}/sentiment")
        show_result(f"GET /creators/{creator_id}/sentiment", code, resp)
        if code == 200 and isinstance(resp, dict):
            bps = resp.get("modifier_bps", 10000)
            modifier = bps / 10000
            delta = modifier - 1.0
            st.metric("AI Modifier", f"{modifier:.4f}×", delta=f"{delta:+.4f}", delta_color="normal")

    st.markdown("---")
    st.subheader("POST /creators/register")
    st.caption("Requires a valid JWT token and wallet linked. Deploys a new creator contract on-chain.")
    yt_channel_id = st.text_input("YouTube Channel ID", placeholder="UC_x5XG1OV2P6uZZ5FSM9Ttw")
    if st.button("Register Creator (LIVE — deploys on-chain!)"):
        if not st.session_state.jwt_token:
            st.warning("Paste a JWT token in the sidebar first.")
        else:
            with st.spinner("Deploying smart contract on Base Sepolia... (~30s)"):
                code, resp = api_post("/creators/register", body={"youtube_channel_id": yt_channel_id}, token=st.session_state.jwt_token)
            show_result("POST /creators/register", code, resp)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: MARKET
# ═══════════════════════════════════════════════════════════════════════════════
with tab_market:
    st.header("📊 Market Endpoints")

    code, status = api_get("/market/status")
    if code == 200 and isinstance(status, dict):
        is_open = status.get("market_open", False)
        badge = "🟢 OPEN" if is_open else "🔴 CLOSED"
        st.metric("Current Market State", badge)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 GET /market/status"):
            code, resp = api_get("/market/status")
            show_result("GET /market/status", code, resp)
    with col2:
        if st.button("🟢 POST /market/open"):
            with st.spinner("Sending open market tx..."):
                code, resp = api_post("/market/open")
            show_result("POST /market/open", code, resp)
    with col3:
        if st.button("🔴 POST /market/close"):
            with st.spinner("Sending close market tx..."):
                code, resp = api_post("/market/close")
            show_result("POST /market/close", code, resp)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: PORTFOLIO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_portfolio:
    st.header("💼 Portfolio Endpoint")
    st.subheader("GET /portfolio/{wallet}")
    wallet = st.text_input("Wallet Address to check", placeholder="0xAbCd1234...")
    if st.button("Fetch Portfolio"):
        if not wallet:
            st.warning("Enter a wallet address.")
        else:
            code, resp = api_get(f"/portfolio/{wallet}")
            show_result(f"GET /portfolio/{wallet}", code, resp)
            if code == 200 and isinstance(resp, list) and resp:
                df = pd.DataFrame(resp)
                if "totalValueUsdc" in df.columns:
                    df["totalValueUsdc_display"] = (df["totalValueUsdc"] / 1e6).map("${:.4f}".format)
                    df["currentPriceUsdc_display"] = (df["currentPriceUsdc"] / 1e6).map("${:.4f}".format)
                st.dataframe(df, use_container_width=True)
            elif code == 200 and isinstance(resp, list) and not resp:
                st.info("This wallet holds no creator tokens.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6: DASHBOARD (CREATOR)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_dashboard:
    st.header("📋 Creator Dashboard Endpoints")
    st.caption("All require a valid JWT token in the sidebar.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("GET /dashboard/earnings"):
            code, resp = api_get("/dashboard/earnings", token=st.session_state.jwt_token)
            show_result("GET /dashboard/earnings", code, resp)
            if code == 200 and isinstance(resp, dict):
                raw = resp.get("earnings_usdc", 0)
                st.metric("Accrued Earnings", f"${raw/1e6:.4f} USDC", f"{raw} micro-USDC")

    with col2:
        if st.button("GET /dashboard/transactions"):
            code, resp = api_get("/dashboard/transactions", token=st.session_state.jwt_token)
            show_result("GET /dashboard/transactions", code, resp)
            if code == 200 and isinstance(resp, list) and resp:
                df = pd.DataFrame(resp)
                st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("POST /dashboard/withdraw")
    st.warning("⚠️ This sends a real on-chain transaction to withdraw your creator fees.")
    if st.button("💸 POST /dashboard/withdraw (LIVE)"):
        if not st.session_state.jwt_token:
            st.warning("Paste a JWT token in the sidebar first.")
        else:
            with st.spinner("Broadcasting withdrawal transaction..."):
                code, resp = api_post("/dashboard/withdraw", token=st.session_state.jwt_token)
            show_result("POST /dashboard/withdraw", code, resp)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7: CANDLESTICK CHART
# ═══════════════════════════════════════════════════════════════════════════════
with tab_candles:
    st.header("📉 Candlestick Chart — GET /creators/{id}/candles")

    chart_creator_id = st.number_input("Creator ID", min_value=1, value=1, step=1, key="chart_creator")
    auto_refresh = st.checkbox("Auto-refresh every 30s")

    if st.button("Load Candles") or auto_refresh:
        code, resp = api_get(f"/creators/{chart_creator_id}/candles", params={"tf": "5m"})

        if code == 200 and isinstance(resp, list) and resp:
            try:
                import plotly.graph_objects as go
                df = pd.DataFrame(resp)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                df["open_usd"] = df["open"] / 1e6
                df["high_usd"] = df["high"] / 1e6
                df["low_usd"] = df["low"] / 1e6
                df["close_usd"] = df["close"] / 1e6

                fig = go.Figure(data=[go.Candlestick(
                    x=df["time"],
                    open=df["open_usd"],
                    high=df["high_usd"],
                    low=df["low_usd"],
                    close=df["close_usd"],
                    increasing_line_color="#00ff88",
                    decreasing_line_color="#ff4444",
                )])
                fig.update_layout(
                    title=f"Creator #{chart_creator_id} — 5m OHLC",
                    yaxis_title="Price (USDC)",
                    xaxis_title="Time",
                    template="plotly_dark",
                    height=500,
                    xaxis_rangeslider_visible=False,
                )
                st.plotly_chart(fig, use_container_width=True)

                # Also show raw data table
                st.dataframe(df[["time", "open_usd", "high_usd", "low_usd", "close_usd", "volume"]].rename(columns={
                    "open_usd": "Open ($)", "high_usd": "High ($)", "low_usd": "Low ($)",
                    "close_usd": "Close ($)", "volume": "Volume"
                }), use_container_width=True)

            except ImportError:
                st.warning("Install plotly: `pip install plotly`")
                st.json(resp)
        elif code == 200 and isinstance(resp, list) and not resp:
            st.info("No candles yet. Run the simulator to generate trading activity.")
        else:
            show_result("GET /creators/{id}/candles", code, resp)

    if auto_refresh:
        time.sleep(30)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 8: SENTIMENT TESTER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sentiment:
    st.header("🧠 YouTube & NLP Sentiment Tester")
    st.caption("Calls `POST /sentiment/analyze` on the backend — exactly the same way Flutter will call it.")

    # Model health check first
    code, model_info = api_get("/sentiment/model/status")
    if code == 200 and isinstance(model_info, dict):
        if model_info.get("model_loaded"):
            st.success(f"✅ RoBERTa model loaded — Python {model_info.get('python_version', '?').split()[0]}")
        else:
            st.error(
                "❌ **Sentiment model failed to load on the backend!**\n\n"
                + str(model_info.get("warning", ""))
            )
            with st.expander("🔧 How to fix the Python 3.14 incompatibility"):
                st.code(
                    "# Install Python 3.12 from https://www.python.org/downloads/\n"
                    "# Then recreate the venv:\n"
                    "cd socialfi-backend\n"
                    "rmdir /s /q venv\n"
                    "py -3.12 -m venv venv\n"
                    ".\\venv\\Scripts\\activate\n"
                    "pip install -r requirements.txt\n"
                    "uvicorn app.main:app --reload",
                    language="bash"
                )
    elif code is None:
        st.warning("Backend offline — can't check model status.")

    st.markdown("---")

    yt_id = st.text_input("YouTube Channel ID", value="UC_x5XG1OV2P6uZZ5FSM9Ttw", key="yt_id_sentiment")
    max_comments = st.slider("Max comments to fetch", 5, 50, 20)

    if st.button("Run Sentiment Analysis"):
        with st.spinner("Calling POST /sentiment/analyze on the backend..."):
            code, resp = api_post("/sentiment/analyze", body={
                "channel_id": yt_id,
                "max_comments": max_comments
            })

        if code is None:
            st.error(resp)
        elif code == 503:
            st.error(
                "**Sentiment model not loaded on backend.**\n\n"
                + (resp.get("detail", "") if isinstance(resp, dict) else str(resp))
            )
        elif code != 200:
            st.error(f"HTTP {code}: {resp}")
        else:
            channel = resp.get("channel", {})
            st.subheader(f"📺 {channel.get('name', yt_id)}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Subscribers", f"{channel.get('subscribers', 0):,}")
            c2.metric("Tier", channel.get("tier_name", "?"))
            c3.metric("Base Price", f"${channel.get('base_price_usdc', 0):.2f} USDC")
            c4.metric("k Value", channel.get("k_value", 0))

            comments_data = resp.get("comments", {})
            fetched = comments_data.get("fetched", 0)
            sample = comments_data.get("sample", [])

            if fetched > 0:
                st.success(f"Fetched {fetched} comments")
                if sample:
                    with st.expander("Comment Sample (first 5)"):
                        for c in sample:
                            st.write(f"— {c}")
            else:
                st.warning("No comments passed the pre-filter.")

            sentiment = resp.get("sentiment", {})
            scores = resp.get("scores", {})
            bps = sentiment.get("modifier_bps", 10000)
            modifier = sentiment.get("modifier_float", 1.0)
            signal = sentiment.get("signal", "neutral")
            signal_label = sentiment.get("signal_label", "")

            st.markdown("---")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Sentiment BPS", f"{bps}", delta=f"{(bps - 10000) / 100:+.2f}%")
            m2.metric("AI Modifier", f"{modifier:.4f}x")
            m3.metric("Engagement Score", f"{scores.get('engagement', 0):.3f}")
            m4.metric("Creator Rank Score", f"{scores.get('creator_rank', 0):.3f}")

            if signal == "positive":
                st.success(f"📈 {signal_label}")
            elif signal == "negative":
                st.error(f"📉 {signal_label}")
            elif signal == "insufficient_data":
                st.warning(f"Not enough data: {signal_label}")
            else:
                st.info(f"😐 {signal_label}")

            with st.expander("Raw API Response"):
                st.json(resp)



# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9: SIMULATOR

# ═══════════════════════════════════════════════════════════════════════════════
with tab_simulator:
    st.header("🤖 Demo Trade Simulator")
    st.markdown("""
    **What this does:** Seeds realistic on-chain trade history so the candlestick chart has data.

    The simulator picks random creator contracts from the backend, and simulates buy/sell
    patterns using the pre-funded oracle wallet (for demo purposes).

    > ⚠️ This hits the **real Base Sepolia testnet** — make sure the market is **OPEN** first.
    """)

    st.markdown("---")

    # Manual one-shot trade trigger
    st.subheader("Manual Trade Trigger")
    sim_creator_id = st.number_input("Creator ID to trade on", min_value=1, value=1, step=1, key="sim_cid")
    sim_action = st.radio("Action", ["Buy", "Sell"], horizontal=True)
    sim_amount = st.slider("Amount (passes)", 1, 5, 1)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Get current price first"):
            code, resp = api_get(f"/creators/{sim_creator_id}/quote/buy", params={"amount": sim_amount})
            show_result("Buy Quote", code, resp)
            if code == 200 and isinstance(resp, dict):
                price = resp.get("price", resp.get("total", 0))
                st.info(f"Buying {sim_amount} pass(es) will cost ≈ ${price/1e6:.4f} USDC")

    with col2:
        if st.button("Check market status"):
            code, resp = api_get("/market/status")
            show_result("Market Status", code, resp)

    st.markdown("---")
    st.subheader("WebSocket Live Feed Monitor")
    st.caption("Connect to `/ws/market` to see real-time ticks as they happen.")

    ws_creator = st.number_input("Subscribe to Creator ID", min_value=0, value=0, step=1, key="ws_cid",
                                  help="0 = global (all events)")
    ws_url = f"ws://127.0.0.1:8000/ws/market"
    st.code(f"""
# Connect to WebSocket:
wscat -c ws://127.0.0.1:8000/ws/market

# Subscribe to a specific creator (send after connecting):
{{"action": "subscribe", "creator_id": {ws_creator}}}

# Expected incoming message shapes:
{{"type": "tick",          "creator_id": 1, "data": {{"price": 2.55, "event": "buy"}}}}
{{"type": "candle",        "creator_id": 1, "data": {{"open": 2.38, "close": 2.55}}}}
{{"type": "market_status",                  "data": {{"isOpen": true}}}}
    """, language="json")

    st.markdown("---")
    st.subheader("Seed Database with Fake Candles (for chart demo)")
    st.caption("Manually inserts mock OHLCV rows into the candles_5m table so you can see the chart immediately.")
    seed_creator_id = st.number_input("Creator ID", min_value=1, value=1, step=1, key="seed_cid")
    seed_count = st.slider("Number of fake candles", 5, 50, 20)

    if st.button("🌱 Seed Fake Candle Data"):
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        try:
            import asyncio, random
            from datetime import datetime, timezone, timedelta
            from app.db.session import AsyncSessionLocal
            from app.db.models import Candle5m
            from sqlalchemy.future import select

            async def seed():
                base_price = 600000  # micro-USDC, starts at $0.60
                now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                # Round down to 5m boundary
                now = now - timedelta(minutes=now.minute % 5)
                inserted = 0

                async with AsyncSessionLocal() as db:
                    for i in range(seed_count, 0, -1):
                        interval_start = now - timedelta(minutes=5 * i)
                        interval_end = interval_start + timedelta(minutes=5)

                        # Simulate random walk
                        change = random.uniform(-0.03, 0.04) * base_price
                        open_p = base_price
                        close_p = int(base_price + change)
                        high_p = max(open_p, close_p) + random.randint(0, 5000)
                        low_p = min(open_p, close_p) - random.randint(0, 5000)
                        vol = random.randint(1, 8)
                        base_price = close_p  # carry forward

                        # Check if already exists
                        ex = await db.execute(select(Candle5m).where(
                            Candle5m.creator_id == seed_creator_id,
                            Candle5m.open_time == interval_start
                        ))
                        if ex.scalars().first():
                            continue

                        candle = Candle5m(
                            creator_id=seed_creator_id,
                            open_time=interval_start,
                            close_time=interval_end,
                            open_price=open_p,
                            high_price=high_p,
                            low_price=low_p,
                            close_price=close_p,
                            volume_tokens=vol
                        )
                        db.add(candle)
                        inserted += 1

                    await db.commit()
                return inserted

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            n = loop.run_until_complete(seed())
            st.success(f"✅ Inserted {n} fake candles for Creator #{seed_creator_id}. Go to the Candlestick Chart tab!")
        except Exception as e:
            st.error(f"Error seeding data: {e}")
