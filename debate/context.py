"""Build Markdown market snapshot for MNQ debate prompts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class SnapshotMeta:
    symbol: str
    interval_primary: str
    bar_count: int
    last_bar_time: str


def synthetic_ohlcv_for_tests(n: int = 120, *, seed: int = 42) -> pd.DataFrame:
    """Deterministic OHLCV DataFrame for tests (no yfinance)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    base = 25000.0 + np.cumsum(rng.normal(0, 2.0, size=n))
    noise = rng.normal(0, 1.0, size=n)
    high = base + np.abs(noise) + 0.5
    low = base - np.abs(noise) - 0.5
    close = base + rng.normal(0, 0.5, size=n)
    open_ = np.r_[base[0], close[:-1]]
    vol = rng.integers(100, 1000, size=n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def _fmt_ts(ts) -> str:
    if hasattr(ts, "strftime"):
        return str(ts)
    return str(ts)


def build_market_snapshot(
    *,
    symbol: str,
    df_5m: pd.DataFrame,
    df_1m: Optional[pd.DataFrame] = None,
    signals_5m: Optional[pd.DataFrame] = None,
) -> tuple[str, SnapshotMeta]:
    """
    Facts-only Markdown snapshot from indicator-enriched OHLCV (5m primary).
    """
    if df_5m.empty or "Close" not in df_5m.columns:
        return ("# MNQ snapshot\n\n(No data)\n", SnapshotMeta(symbol, "5m", 0, ""))

    last = df_5m.iloc[-1]
    last_idx = df_5m.index[-1]
    last_ts = _fmt_ts(last_idx)

    close = float(last["Close"])
    lines = [
        "# MNQ market snapshot",
        "",
        f"- **Symbol (as fetched)**: `{symbol}`",
        f"- **Primary interval**: 5m bars, count={len(df_5m)}",
        f"- **Last bar time (index)**: {last_ts}",
        f"- **Last OHLCV**: O={float(last.get('Open', float('nan'))):.2f} H={last['High']:.2f} "
        f"L={last['Low']:.2f} C={close:.2f} V={float(last.get('Volume', float('nan'))):.0f}",
        "",
        "## Indicators (last bar, 5m)",
    ]

    if "VWAP" in df_5m.columns and pd.notna(last.get("VWAP")):
        vwap = float(last["VWAP"])
        lines.append(f"- **VWAP**: {vwap:.2f} (close vs VWAP: {close - vwap:+.2f})")
    if "sma_20" in df_5m.columns and pd.notna(last.get("sma_20")):
        lines.append(f"- **SMA 20**: {float(last['sma_20']):.2f}")
    if "sma_50" in df_5m.columns and pd.notna(last.get("sma_50")):
        lines.append(f"- **SMA 50**: {float(last['sma_50']):.2f}")
    if all(c in df_5m.columns for c in ("sma_20", "sma_50")) and pd.notna(
        last.get("sma_20")
    ) and pd.notna(last.get("sma_50")):
        trend = "up" if float(last["sma_20"]) > float(last["sma_50"]) else "down"
        lines.append(f"- **SMA stack**: SMA20 vs SMA50 → **{trend}** (heuristic)")
    if all(c in df_5m.columns for c in ("bb_upper", "bb_lower", "bb_middle")):
        bu, bl, bm = float(last["bb_upper"]), float(last["bb_lower"]), float(last["bb_middle"])
        lines.append(f"- **Bollinger (20,2)**: upper={bu:.2f} mid={bm:.2f} lower={bl:.2f}")

    if df_1m is not None and not df_1m.empty and "Close" in df_1m.columns:
        c1 = float(df_1m["Close"].iloc[-1])
        lines.extend(["", "## 1m context (last close only)", f"- **1m last close**: {c1:.2f}"])

    lines.extend(["", "## Recent 5m strategy alerts (from repo rules)"])
    if signals_5m is not None and not signals_5m.empty:
        tail = signals_5m.tail(8)
        for _, row in tail.iterrows():
            lines.append(
                f"- {_fmt_ts(row['timestamp'])} **{row['signal']}** @ {float(row['price']):.2f}"
            )
    else:
        lines.append("- (none in window)")

    lines.extend(["", "## Your task", "Use only the facts above. Output JSON per the role instructions."])

    meta = SnapshotMeta(
        symbol=symbol,
        interval_primary="5m",
        bar_count=len(df_5m),
        last_bar_time=last_ts,
    )
    return "\n".join(lines) + "\n", meta
