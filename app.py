"""Streamlit app — fully automatic MNQ multi-model debate.

Models called automatically via API keys in .env:
  TrendAgent    → GPT-4o      (OpenAI)
  MeanRevertAgent → Gemini 1.5 Pro  (Google)
  RiskAgent     → Claude Sonnet 3.5 (Anthropic)
  Chair         → Claude Opus       (Anthropic)

Run:
    streamlit run app.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from debate.context import build_market_snapshot, synthetic_ohlcv_for_tests
from debate.llm_callers import (
    GEMINI_MODEL,
    OPENAI_MODEL,
    OPUS_MODEL,
    SONNET_MODEL,
    anthropic_mode,
    call_anthropic,
    call_gemini,
    call_openai,
    call_opus,
)
from debate.prompts import (
    CHAIR_SYSTEM,
    DISCLAIMER,
    JSON_AGENT_CONTRACT,
    JSON_CHAIR_CONTRACT,
    ROLE_MEANREV,
    ROLE_RISK,
    ROLE_TREND,
)
from debate.schema import parse_json_object, validate_agent_reply, validate_chair_reply

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="MNQ Debate",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helper: pick display name based on which Anthropic backend is configured
# ---------------------------------------------------------------------------
def _claude_agent_name(preferred: str) -> str:
    if os.environ.get("CLAUDE_PROXY_URL", "").strip():
        return f"{preferred}  (subscription proxy)"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return f"{preferred}  (API key)"
    return f"GPT-4o  (fallback — set CLAUDE_PROXY_URL or ANTHROPIC_API_KEY)"


# ---------------------------------------------------------------------------
# Agent definitions — edit model strings here to change lineup
# ---------------------------------------------------------------------------
AGENTS = [
    {
        "key": "trend",
        "label": "TrendAgent",
        "model_name": f"GPT-4o  ({OPENAI_MODEL})",
        "role_prompt": ROLE_TREND,
        "caller": lambda s, u: call_openai(s, u),
        "icon": "🟦",
    },
    {
        "key": "meanrev",
        "label": "MeanRevertAgent",
        "model_name": f"Gemini 2.5 Flash  ({GEMINI_MODEL})",
        "role_prompt": ROLE_MEANREV,
        "caller": lambda s, u: call_gemini(s, u),
        "icon": "🟩",
    },
    {
        "key": "risk",
        "label": "RiskAgent",
        "model_name": _claude_agent_name("Claude Sonnet"),
        "role_prompt": ROLE_RISK,
        "caller": lambda s, u: call_anthropic(s, u),
        "icon": "🟧",
    },
]

CHAIR_META = {"label": "Chair", "model_name": _claude_agent_name("Claude Opus"), "icon": "🪑"}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_ss = st.session_state
_ss.setdefault("snapshot_md", None)
_ss.setdefault("df_5m", None)
_ss.setdefault("fetched_at", None)
_ss.setdefault("debate_done", False)
for a in AGENTS:
    _ss.setdefault(f"raw_{a['key']}", None)
    _ss.setdefault(f"parsed_{a['key']}", None)
_ss.setdefault("raw_chair", None)
_ss.setdefault("parsed_chair", None)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _side_badge(side: str) -> str:
    icons = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}
    return f"{icons.get(side, '⚪')} **{side.upper()}**"


def _confidence_bar(conf: float) -> None:
    pct = int(conf * 100)
    colour = "#28a745" if conf >= 0.6 else "#ffc107" if conf >= 0.4 else "#dc3545"
    st.markdown(
        f'<div style="background:#e9ecef;border-radius:6px;height:22px">'
        f'<div style="background:{colour};width:{pct}%;height:22px;border-radius:6px;'
        f'display:flex;align-items:center;padding-left:8px;color:#fff;font-size:13px">'
        f"{pct}%</div></div>",
        unsafe_allow_html=True,
    )


def _agent_system(role_prompt: str) -> str:
    return f"{role_prompt}\n\n{JSON_AGENT_CONTRACT}"


def _chair_user(snapshot_md: str) -> str:
    parts = []
    for a in AGENTS:
        parsed = _ss[f"parsed_{a['key']}"]
        if parsed is not None:
            parts.append(f"### {a['label']}\n```json\n{json.dumps(parsed, indent=2)}\n```")
    agent_block = "\n\n".join(parts)
    return f"{snapshot_md}\n\n---\n## Agent replies\n\n{agent_block}"


def _mini_chart(df: pd.DataFrame) -> None:
    tail = df.tail(40)
    fig, ax = plt.subplots(figsize=(6, 2.2))
    ax.plot(tail.index, tail["Close"], linewidth=1.5, color="#1f77b4", label="Close")
    if "VWAP" in tail:
        ax.plot(tail.index, tail["VWAP"], linewidth=1, color="#ff7f0e",
                linestyle="--", label="VWAP")
    if "sma_20" in tail:
        ax.plot(tail.index, tail["sma_20"], linewidth=0.8, color="#2ca02c",
                linestyle=":", label="SMA20")
    ax.legend(fontsize=8)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


def _check_keys() -> list[str]:
    """Return list of missing required env var names."""
    missing = []
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        missing.append("GOOGLE_API_KEY")
    # ANTHROPIC_API_KEY is optional — app falls back to GPT-4o if absent
    return missing


def _do_fetch(symbol: str, fallback: str, period: str, dry_run: bool) -> None:
    if dry_run:
        df_5m = synthetic_ohlcv_for_tests(120)
        df_1m = synthetic_ohlcv_for_tests(60, seed=99)
        from mnq_data import add_indicators, compute_signals_5m
        df_5m = add_indicators(df_5m)
        df_1m = add_indicators(df_1m)
        sigs = compute_signals_5m(df_5m)
        used = f"{symbol} [dry-run]"
    else:
        from mnq_data import add_indicators, compute_signals_5m, download_with_fallback
        df_5m_raw, used = download_with_fallback(symbol, fallback, "5m", period=period)
        df_1m_raw, _ = download_with_fallback(symbol, fallback, "1m", period=period)
        df_5m = add_indicators(df_5m_raw) if not df_5m_raw.empty else df_5m_raw
        df_1m = add_indicators(df_1m_raw) if not df_1m_raw.empty else df_1m_raw
        sigs = compute_signals_5m(df_5m) if not df_5m.empty else pd.DataFrame()

    snap_md, _ = build_market_snapshot(
        symbol=used, df_5m=df_5m, df_1m=df_1m,
        signals_5m=sigs if not sigs.empty else None,
    )
    _ss.snapshot_md = snap_md
    _ss.df_5m = df_5m
    _ss.fetched_at = pd.Timestamp.now().strftime("%H:%M:%S")
    # reset previous debate
    _ss.debate_done = False
    for a in AGENTS:
        _ss[f"raw_{a['key']}"] = None
        _ss[f"parsed_{a['key']}"] = None
    _ss.raw_chair = None
    _ss.parsed_chair = None


def _run_debate() -> None:
    """Call all agents then the chair; store results in session state."""
    with st.status("Running debate…", expanded=True) as status:
        for agent in AGENTS:
            key = agent["key"]
            st.write(f"{agent['icon']} Calling **{agent['label']}** via {agent['model_name']}…")
            try:
                raw = agent["caller"](
                    _agent_system(agent["role_prompt"]),
                    _ss.snapshot_md,
                )
                _ss[f"raw_{key}"] = raw
                parsed = validate_agent_reply(parse_json_object(raw))
                _ss[f"parsed_{key}"] = parsed
                st.write(f"   ✅ {agent['label']}: **{parsed['side'].upper()}** "
                         f"@ {parsed.get('entry_price') or '—'}  "
                         f"(conf {parsed['confidence']:.0%})")
            except Exception as exc:
                _ss[f"parsed_{key}"] = None
                st.write(f"   ❌ {agent['label']} failed: {exc}")

        valid = sum(1 for a in AGENTS if _ss[f"parsed_{a['key']}"] is not None)
        if valid < 2:
            status.update(label="Debate incomplete — fewer than 2 agents succeeded.", state="error")
            return

        st.write(f"{CHAIR_META['icon']} Calling **Chair** via {CHAIR_META['model_name']}…")
        try:
            raw_chair = call_opus(CHAIR_SYSTEM + f"\n\n{JSON_CHAIR_CONTRACT}", _chair_user(_ss.snapshot_md))
            _ss.raw_chair = raw_chair
            _ss.parsed_chair = validate_chair_reply(parse_json_object(raw_chair))
            c = _ss.parsed_chair
            st.write(f"   ✅ Chair verdict: **{c['side'].upper()}** "
                     f"@ {c.get('entry_price') or '—'}  "
                     f"(conf {c['confidence']:.0%})")
        except Exception as exc:
            _ss.parsed_chair = None
            st.write(f"   ❌ Chair failed: {exc}")
            status.update(label="Chair call failed.", state="error")
            return

        _ss.debate_done = True
        status.update(label="Debate complete ✓", state="complete", expanded=False)


# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Settings")
    symbol = st.text_input("Symbol", value="MNQM26.CME")
    fallback = st.text_input("Fallback", value="MNQ=F")
    period = st.selectbox("Period", ["1d", "2d", "5d", "7d"], index=2)
    dry_run = st.checkbox("Dry-run (synthetic data, no yfinance)", value=False)

    st.divider()
    missing = _check_keys()
    if missing:
        st.error("Missing in .env:\n" + "\n".join(f"• `{k}`" for k in missing))
        st.markdown("Copy `.env.example` → `.env` and fill in keys.")
    else:
        st.success("API keys loaded ✓")

    ant_mode = anthropic_mode()
    if "proxy" in ant_mode:
        st.info("RiskAgent + Chair → **Claude subscription** (proxy) ✓")
    elif "API key" in ant_mode:
        st.info("RiskAgent + Chair → **Claude Sonnet / Opus** (API key) ✓")
    else:
        st.warning(
            "RiskAgent + Chair → **GPT-4o** fallback.\n\n"
            "To use Claude subscription instead:\n"
            "1. `npm install -g @anthropic-ai/claude-code`\n"
            "2. `claude auth login`\n"
            "3. `npm install -g claude-max-api-proxy && claude-max-api`\n"
            "4. Add `CLAUDE_PROXY_URL=http://localhost:3456/v1` to `.env`"
        )

    st.divider()
    st.caption(DISCLAIMER)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("📊 MNQ Multi-Model Debate")
_has_claude = bool(os.environ.get("CLAUDE_PROXY_URL") or os.environ.get("ANTHROPIC_API_KEY"))
st.caption(
    "TrendAgent → **GPT-4o** &nbsp;|&nbsp; "
    "MeanRevertAgent → **Gemini 2.5 Flash** &nbsp;|&nbsp; "
    f"RiskAgent → **{'Claude Sonnet' if _has_claude else 'GPT-4o'}** &nbsp;|&nbsp; "
    f"Chair → **{'Claude Opus' if _has_claude else 'GPT-4o'}**"
)

# ---------------------------------------------------------------------------
# Step 1 — Fetch snapshot
# ---------------------------------------------------------------------------
col_fetch, col_run = st.columns([1, 1])

with col_fetch:
    if st.button("🔄 Fetch snapshot", use_container_width=True, type="primary"):
        with st.spinner("Downloading market data…"):
            _do_fetch(symbol, fallback, period, dry_run)
        st.rerun()

with col_run:
    run_disabled = _ss.snapshot_md is None or bool(missing)
    if st.button(
        "▶ Run debate",
        use_container_width=True,
        type="primary",
        disabled=run_disabled,
        help="Fetch a snapshot first, and ensure API keys are set in .env",
    ):
        _run_debate()
        st.rerun()

if _ss.fetched_at:
    st.caption(f"Snapshot fetched at {_ss.fetched_at}")

if _ss.snapshot_md is None:
    st.info("Click **Fetch snapshot** to begin.")
    st.stop()

# Snapshot preview
with st.expander("📋 Market snapshot", expanded=not _ss.debate_done):
    col_md, col_chart = st.columns([1, 1])
    with col_md:
        st.markdown(_ss.snapshot_md)
    with col_chart:
        if _ss.df_5m is not None and not _ss.df_5m.empty:
            _mini_chart(_ss.df_5m)

# ---------------------------------------------------------------------------
# Agent cards (shown after debate runs)
# ---------------------------------------------------------------------------
if any(_ss[f"parsed_{a['key']}"] is not None for a in AGENTS):
    st.divider()
    st.subheader("Agent opinions")
    cols = st.columns(len(AGENTS))
    for col, agent in zip(cols, AGENTS):
        p = _ss[f"parsed_{agent['key']}"]
        with col:
            st.markdown(f"**{agent['icon']} {agent['label']}**")
            st.caption(agent["model_name"])
            if p:
                side_icon = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(p["side"], "⚪")
                st.markdown(f"### {side_icon} {p['side'].upper()}")
                st.metric("Entry", f"{p['entry_price']:.2f}" if p.get("entry_price") else "—")
                st.metric("Confidence", f"{p['confidence']:.0%}")
                with st.expander("Rationale"):
                    st.write(p.get("rationale", "—"))
            else:
                st.warning("Failed / not run")

# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------
if _ss.parsed_chair is not None:
    st.divider()
    chair = _ss.parsed_chair

    st.subheader(f"{CHAIR_META['icon']} Final verdict  ·  {CHAIR_META['model_name']}")

    v1, v2, v3 = st.columns(3)
    v1.markdown(f"## {_side_badge(chair['side'])}")
    v2.metric("Entry price", f"{chair['entry_price']:.2f}" if chair.get("entry_price") else "—")
    with v3:
        st.markdown("**Confidence**")
        _confidence_bar(chair.get("confidence", 0))

    st.markdown(f"**Rationale:** {chair.get('rationale', '')}")
    if chair.get("dissent_summary"):
        st.info(f"**Dissent:** {chair['dissent_summary']}")

    st.caption(DISCLAIMER)

    # Download full record
    record = {
        "fetched_at": _ss.fetched_at,
        "agents": {
            a["key"]: {
                "model": a["model_name"],
                "reply": _ss[f"parsed_{a['key']}"],
            }
            for a in AGENTS
        },
        "chair": {"model": CHAIR_META["model_name"], "reply": chair},
    }
    st.download_button(
        "⬇ Download debate JSON",
        data=json.dumps(record, indent=2, default=str),
        file_name="mnq_debate.json",
        mime="application/json",
    )
