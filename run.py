"""
MNQ (Micro E-mini Nasdaq-100) 1m and 5m candles from Yahoo Finance.
Computes VWAP (session-based), volume, Bollinger Bands, SMA; plots two dashboards.
"""
import os

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(__file__), ".matplotlib"))
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mnq_data import (
    FALLBACK_SYMBOL,
    PERIOD,
    SYMBOL,
    add_indicators,
    compute_signals_5m,
    download_candles,
)


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
    """Top: Close, VWAP, SMA(s), Bollinger. Bottom: Volume. Optional BUY/SELL markers."""
    if df.empty or "Close" not in df.columns:
        return
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    x = df.index

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
        df = download_candles(symbol, interval, period=PERIOD)
        if df.empty and symbol != FALLBACK_SYMBOL:
            print(f"No {interval} data for {symbol}, trying {FALLBACK_SYMBOL}")
            symbol = FALLBACK_SYMBOL
            df = download_candles(symbol, interval, period=PERIOD)
        if df.empty:
            print(f"No data for {interval}. Skipping.")
            continue
        symbol_used = symbol

        df = add_indicators(df)

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
