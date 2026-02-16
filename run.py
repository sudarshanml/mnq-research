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


def compute_signals_5m(df: pd.DataFrame) -> pd.DataFrame:
    """
    5m trend strategy: BUY in uptrend (SMA20 > SMA50) with Close > SMA20 and Close > VWAP;
    SELL when downtrend confirmed (SMA20 < SMA50 and Close < SMA20 for 2 consecutive bars).
    One BUY per cycle until SELL; one SELL per cycle until next BUY.
    Returns DataFrame with columns: timestamp, signal, price.
    """
    required = ["Close", "VWAP", "sma_20", "sma_50"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame(columns=["timestamp", "signal", "price"])
    close = df["Close"]
    sma_20 = df["sma_20"]
    sma_50 = df["sma_50"]
    vwap = df["VWAP"]
    # Valid where we have both SMAs (avoid NaN in first ~50 bars)
    valid = sma_20.notna() & sma_50.notna()
    uptrend = (sma_20 > sma_50) & valid
    downtrend = (sma_20 < sma_50) & valid
    above_sma20 = (close > sma_20) & valid
    above_vwap = (close > vwap) | vwap.isna()
    buy_cond = uptrend & above_sma20 & above_vwap
    # Confirmed downtrend: 2 consecutive bars with Close < SMA20
    below_sma20 = (close < sma_20) & valid
    two_bars_below = below_sma20.rolling(2, min_periods=2).sum() == 2
    sell_cond = downtrend & two_bars_below
    # State machine: emit one BUY then one SELL per cycle
    alerts = []
    in_position = False
    for i in range(len(df)):
        if buy_cond.iloc[i] and not in_position:
            alerts.append({"timestamp": df.index[i], "signal": "BUY", "price": close.iloc[i]})
            in_position = True
        elif sell_cond.iloc[i] and in_position:
            alerts.append({"timestamp": df.index[i], "signal": "SELL", "price": close.iloc[i]})
            in_position = False
    return pd.DataFrame(alerts)


def print_alerts(signals_df: pd.DataFrame) -> None:
    """Print each alert to console: BUY/SELL, timestamp, price."""
    if signals_df.empty:
        print("No 5m strategy alerts.")
        return
    for _, row in signals_df.iterrows():
        ts = row["timestamp"]
        if hasattr(ts, "strftime"):
            ts_str = ts.strftime("%Y-%m-%d %H:%M")
        else:
            ts_str = str(ts)
        print(f"  {row['signal']:4}  {ts_str}  {row['price']:.2f}")
    print(f"Total: {len(signals_df)} alert(s).")


def write_alerts_csv(signals_df: pd.DataFrame, path: str = "alerts_5m.csv") -> None:
    """Append alerts to CSV with columns timestamp, signal, price."""
    if signals_df.empty:
        return
    out = signals_df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    write_header = not os.path.exists(path)
    out.to_csv(path, index=False, mode="a", header=write_header)
    print(f"Appended alerts to {path}")


def plot_dashboard(
    df: pd.DataFrame,
    title: str,
    interval_label: str,
    save_path: str,
    signals_df: pd.DataFrame | None = None,
) -> None:
    """Top: Close, VWAP, SMA(s), Bollinger. Bottom: Volume. Optional BUY/SELL markers from signals_df."""
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
    # BUY/SELL markers
    if signals_df is not None and not signals_df.empty and "timestamp" in signals_df.columns:
        for _, row in signals_df.iterrows():
            t, sig, price = row["timestamp"], row["signal"], row["price"]
            color = "green" if sig == "BUY" else "red"
            ax1.axvline(x=t, color=color, alpha=0.5, linestyle="--", linewidth=1)
            ax1.scatter([t], [price], color=color, s=40, zorder=5, marker="^" if sig == "BUY" else "v")
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

        # 5m strategy: buy/sell alerts and optional chart markers
        signals_df = pd.DataFrame(columns=["timestamp", "signal", "price"])
        if label == "5m":
            signals_df = compute_signals_5m(df)
            print("5m strategy alerts:")
            print_alerts(signals_df)
            write_alerts_csv(signals_df)

        title = f"MNQ {label} — {symbol_used}"
        save_path = f"mnq_{label}_indicators.png"
        plot_dashboard(df, title, label, save_path, signals_df=signals_df if label == "5m" else None)

    print("Done.")


if __name__ == "__main__":
    main()
