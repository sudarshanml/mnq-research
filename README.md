# MNQ Trading Research

Micro E-mini Nasdaq-100 (MNQ) futures research: pull 1‑minute and 5‑minute candles from Yahoo Finance, compute VWAP, Bollinger Bands, and SMAs, and plot dashboards.

## What it does

- **Data**: Downloads up to 7 days of 1m and 5m OHLCV for `MNQM26.CME` (fallback: `MNQ=F`) via yfinance.
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

## MNQ debate — web UI (Cursor, no API keys)

Run a browser-based debate workflow.  Models run in Cursor alongside the app; no API keys needed.

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.  Workflow:

1. **Sidebar** — enter symbol, pick period, click **Fetch snapshot** (or enable dry-run for offline use).
2. **Snapshot tab** — review market facts and a mini 5m price chart.
3. **Agents tab** — copy each agent prompt → paste into **Cursor Chat** (choose any model) → paste JSON reply back.
4. **Chair tab** — auto-built once ≥2 agent replies are valid; copy → Cursor → paste chair JSON back.
5. **Result tab** — side badge, entry price, confidence bar, rationale, agent vote table, download JSON.

### CLI alternative

```bash
python debate_cli.py          # live data
python debate_cli.py --dry-run  # synthetic / offline
```

Outputs under `out/debate/`: `snapshot.md`, `debate_instructions.md`, `chair_prompt.md`, `replies/README.txt`.

Optional Cursor rule: [.cursor/rules/mnq-debate.mdc](.cursor/rules/mnq-debate.mdc).

## Tests

```bash
python -m unittest discover -s tests -v
```
