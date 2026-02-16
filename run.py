"""
MNQ (Micro E-mini Nasdaq-100) 1m and 5m candles from Yahoo Finance.
Computes VWAP (session-based), volume, Bollinger Bands, SMA; plots two dashboards.
"""
import os
# Use project-local matplotlib config so it works in restricted envs
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(__file__), ".matplotlib"))
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SYMBOL = "MNQH26.CME"
FALLBACK_SYMBOL = "MNQ=F"
PERIOD = "7d"
BB_N = 20
BB_K = 2
SMA_WINDOWS = (20, 50)
CME_SESSION_START_HOUR_ET = 18  # 6:00 PM ET


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure single-level column names (Open, High, Low, Close, Volume)."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def download_candles(symbol: str, interval: str) -> pd.DataFrame:
    """Download intraday candles; return DataFrame with simple column names."""
    # yfinance 1m/5m limited to last 7 days
    df = yf.download(
        symbol,
        period=PERIOD,
        interval=interval,
        progress=False,
        auto_adjust=False,
        prepost=True,
    )
    if df.empty or len(df) < 2:
        return pd.DataFrame()
    df = _flatten_columns(df)
    # Keep OHLCV; drop Adj Close if present
    for c in ("Adj Close", "Adj Close%"):
        if c in df.columns:
            df = df.drop(columns=[c])
    df = df.dropna(how="all")
    return df


def _session_id_et(index: pd.DatetimeIndex) -> pd.Series:
    """Return session id (date of session start in ET) for CME: session starts 6 PM ET."""
    if index.tz is None:
        index = index.tz_localize("UTC", ambiguous="infer")
    et = index.tz_convert("America/New_York")
    # Session that contains this bar: started at 18:00 ET on session_start_date
    # Bar at 10:00 ET Feb 10 -> session started 18:00 ET Feb 9 -> session_date = Feb 9
    session_start = et - pd.Timedelta(hours=CME_SESSION_START_HOUR_ET)
    session_date = session_start.normalize()
    return pd.Series(session_date, index=index)


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-based VWAP: typical_price * volume cumsum / volume cumsum, reset per CME session."""
    if "Volume" not in df.columns or df["Volume"].fillna(0).eq(0).all():
        return pd.Series(np.nan, index=df.index)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].fillna(0)
    session = _session_id_et(df.index)
    tp_v = typical * vol
    vwap = (tp_v.groupby(session).cumsum() / vol.groupby(session).cumsum())
    return vwap.reindex(df.index)


def compute_bollinger(close: pd.Series, n: int = BB_N, k: float = BB_K) -> pd.DataFrame:
    """Bollinger Bands: middle = SMA(close, n), upper/lower = middle ± k * rolling_std(n)."""
    middle = close.rolling(n, min_periods=1).mean()
    std = close.rolling(n, min_periods=1).std()
    upper = middle + k * std
    lower = middle - k * std
    return pd.DataFrame({"bb_upper": upper, "bb_middle": middle, "bb_lower": lower}, index=close.index)


def compute_sma(close: pd.Series, windows: tuple = SMA_WINDOWS) -> pd.DataFrame:
    """Multiple SMAs on close."""
    out = {}
    for w in windows:
        out[f"sma_{w}"] = close.rolling(w, min_periods=1).mean()
    return pd.DataFrame(out, index=close.index)


def plot_dashboard(
    df: pd.DataFrame,
    title: str,
    interval_label: str,
    save_path: str,
) -> None:
    """Top: Close, VWAP, SMA(s), Bollinger. Bottom: Volume. Shared x-axis."""
    if df.empty or "Close" not in df.columns:
        return
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    x = df.index

    # Price and indicators
    ax1.plot(x, df["Close"], color="black", linewidth=1, label="Close")
    if "VWAP" in df.columns and df["VWAP"].notna().any():
        ax1.plot(x, df["VWAP"], color="blue", linewidth=1.5, label="VWAP")
    for col in df.columns:
        if col.startswith("sma_"):
            ax1.plot(x, df[col], linewidth=1, alpha=0.8, label=col.upper())
    if "bb_upper" in df.columns:
        ax1.fill_between(x, df["bb_upper"], df["bb_lower"], alpha=0.2, color="gray")
        ax1.plot(x, df["bb_upper"], color="gray", linewidth=0.8, label="BB Upper")
        ax1.plot(x, df["bb_middle"], color="gray", linewidth=0.8, linestyle="--", label="BB Mid")
        ax1.plot(x, df["bb_lower"], color="gray", linewidth=0.8, label="BB Lower")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left", fontsize=7)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(title)

    # Volume
    vol = df["Volume"].fillna(0) if "Volume" in df.columns else pd.Series(0, index=df.index)
    if "Open" in df.columns:
        up = (df["Close"] >= df["Open"]).fillna(True)
        colors = np.where(up, "green", "red")
    else:
        colors = "steelblue"
    ax2.bar(x, vol, color=colors, alpha=0.7, width=0.8)
    ax2.set_ylabel("Volume")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.xticks(rotation=45)
    fig.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


def main() -> None:
    for interval, label in [("1m", "1m"), ("5m", "5m")]:
        symbol = SYMBOL
        df = download_candles(symbol, interval)
        if df.empty and symbol != FALLBACK_SYMBOL:
            print(f"No {interval} data for {symbol}, trying {FALLBACK_SYMBOL}")
            symbol = FALLBACK_SYMBOL
            df = download_candles(symbol, interval)
        if df.empty:
            print(f"No data for {interval}. Skipping.")
            continue
        symbol_used = symbol

        # Indicators
        close = df["Close"]
        df["VWAP"] = compute_vwap(df)
        bb = compute_bollinger(close)
        df = pd.concat([df, bb], axis=1)
        sma = compute_sma(close)
        df = pd.concat([df, sma], axis=1)

        title = f"MNQ {label} — {symbol_used}"
        save_path = f"mnq_{label}_indicators.png"
        plot_dashboard(df, title, label, save_path)

    print("Done.")


if __name__ == "__main__":
    main()
