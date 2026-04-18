"""Shared MNQ market data: Yahoo Finance download and technical indicators."""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

SYMBOL = "MNQM26.CME"
FALLBACK_SYMBOL = "MNQ=F"
PERIOD = "7d"
BB_N = 20
BB_K = 2
SMA_WINDOWS = (20, 50)
CME_SESSION_START_HOUR_ET = 18  # 6:00 PM ET


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure single-level column names (Open, High, Low, Close, Volume)."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def download_candles(
    symbol: str,
    interval: str,
    *,
    period: str = PERIOD,
) -> pd.DataFrame:
    """Download intraday candles; return DataFrame with simple column names."""
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        prepost=True,
    )
    if df.empty or len(df) < 2:
        return pd.DataFrame()
    df = flatten_columns(df)
    for c in ("Adj Close", "Adj Close%"):
        if c in df.columns:
            df = df.drop(columns=[c])
    df = df.dropna(how="all")
    return df


def download_with_fallback(
    symbol: str = SYMBOL,
    fallback: str = FALLBACK_SYMBOL,
    interval: str = "5m",
    *,
    period: str = PERIOD,
) -> tuple[pd.DataFrame, str]:
    """Try primary symbol then fallback. Returns (df, symbol_used)."""
    df = download_candles(symbol, interval, period=period)
    used = symbol
    if df.empty and symbol != fallback:
        df = download_candles(fallback, interval, period=period)
        used = fallback
    return df, used


def session_id_et(index: pd.DatetimeIndex) -> pd.Series:
    """Session id (date of session start in ET) for CME: session starts 6 PM ET."""
    if index.tz is None:
        index = index.tz_localize("UTC", ambiguous="infer")
    et = index.tz_convert("America/New_York")
    session_start = et - pd.Timedelta(hours=CME_SESSION_START_HOUR_ET)
    session_date = session_start.normalize()
    return pd.Series(session_date, index=index)


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-based VWAP."""
    if "Volume" not in df.columns or df["Volume"].fillna(0).eq(0).all():
        return pd.Series(np.nan, index=df.index)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].fillna(0)
    session = session_id_et(df.index)
    tp_v = typical * vol
    vwap = tp_v.groupby(session).cumsum() / vol.groupby(session).cumsum()
    return vwap.reindex(df.index)


def compute_bollinger(close: pd.Series, n: int = BB_N, k: float = BB_K) -> pd.DataFrame:
    middle = close.rolling(n, min_periods=1).mean()
    std = close.rolling(n, min_periods=1).std()
    upper = middle + k * std
    lower = middle - k * std
    return pd.DataFrame({"bb_upper": upper, "bb_middle": middle, "bb_lower": lower}, index=close.index)


def compute_sma(close: pd.Series, windows: tuple = SMA_WINDOWS) -> pd.DataFrame:
    out = {}
    for w in windows:
        out[f"sma_{w}"] = close.rolling(w, min_periods=1).mean()
    return pd.DataFrame(out, index=close.index)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append VWAP, Bollinger, SMA columns to OHLCV DataFrame."""
    if df.empty or "Close" not in df.columns:
        return df
    close = df["Close"]
    out = df.copy()
    out["VWAP"] = compute_vwap(out)
    bb = compute_bollinger(close)
    sma = compute_sma(close)
    return pd.concat([out, bb, sma], axis=1)


def compute_signals_5m(df: pd.DataFrame) -> pd.DataFrame:
    """5m trend strategy alerts; columns timestamp, signal, price."""
    required = ["Close", "VWAP", "sma_20", "sma_50"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame(columns=["timestamp", "signal", "price"])
    close = df["Close"]
    sma_20 = df["sma_20"]
    sma_50 = df["sma_50"]
    vwap = df["VWAP"]
    valid = sma_20.notna() & sma_50.notna()
    uptrend = (sma_20 > sma_50) & valid
    downtrend = (sma_20 < sma_50) & valid
    above_sma20 = (close > sma_20) & valid
    above_vwap = (close > vwap) | vwap.isna()
    buy_cond = uptrend & above_sma20 & above_vwap
    below_sma20 = (close < sma_20) & valid
    two_bars_below = below_sma20.rolling(2, min_periods=2).sum() == 2
    sell_cond = downtrend & two_bars_below
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
