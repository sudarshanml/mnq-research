# MNQ Trading Research

Micro E-mini Nasdaq-100 (MNQ) futures research: pull 1‑minute and 5‑minute candles from Yahoo Finance, compute VWAP, Bollinger Bands, and SMAs, and plot dashboards.

## What it does

- **Data**: Downloads up to 7 days of 1m and 5m OHLCV for `MNQH26.CME` (fallback: `MNQ=F`) via yfinance.
- **Indicators**: Session-based VWAP (CME session 6 PM–5 PM ET), Bollinger Bands (20-period, k=2), SMA 20 and 50.
- **Plots**: Two PNG dashboards—price with VWAP, SMAs, and Bollinger Bands (top), and volume (bottom).

## Setup

- Python 3.12 recommended.

Create and activate a virtual environment:

```bash
python3 -m venv venv312
source venv312/bin/activate   # Windows: venv312\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python run.py
```

- Fetches 1m and 5m data from Yahoo Finance, computes indicators, and saves:
  - `mnq_1m_indicators.png`
  - `mnq_5m_indicators.png`
