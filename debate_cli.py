#!/usr/bin/env python3
"""Prepare MNQ debate artifacts for Cursor (no LLM API keys)."""
from __future__ import annotations

import argparse
from pathlib import Path

from debate.context import build_market_snapshot, synthetic_ohlcv_for_tests
from debate.packager import write_debate_artifacts
from mnq_data import (
    FALLBACK_SYMBOL,
    PERIOD,
    SYMBOL,
    add_indicators,
    compute_signals_5m,
    download_with_fallback,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Write MNQ debate prompt pack (snapshot + instructions) for Cursor"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Use synthetic OHLCV (no Yahoo); still writes artifacts",
    )
    p.add_argument("--symbol", default=SYMBOL, help="Yahoo Finance symbol")
    p.add_argument("--fallback", default=FALLBACK_SYMBOL, help="Fallback symbol if primary empty")
    p.add_argument("--period", default=PERIOD, help="yfinance period (e.g. 7d)")
    p.add_argument("--out-dir", default="out/debate", help="Output directory")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.dry_run:
        df_5m = synthetic_ohlcv_for_tests(80)
        df_5m = add_indicators(df_5m)
        df_1m = None
        sym = f"{args.symbol} (dry-run synthetic)"
        signals = compute_signals_5m(df_5m)
    else:
        df_5m, sym = download_with_fallback(
            args.symbol, args.fallback, "5m", period=args.period
        )
        if df_5m.empty:
            print("No 5m data; use --dry-run for offline artifacts.")
            return
        df_5m = add_indicators(df_5m)
        df_1m, _ = download_with_fallback(args.symbol, args.fallback, "1m", period=args.period)
        if not df_1m.empty:
            df_1m = add_indicators(df_1m)
        else:
            df_1m = None
        signals = compute_signals_5m(df_5m)

    snapshot_md, meta = build_market_snapshot(
        symbol=sym, df_5m=df_5m, df_1m=df_1m, signals_5m=signals
    )
    out = write_debate_artifacts(args.out_dir, snapshot_md)

    print("MNQ debate artifacts written to:", out.resolve())
    print("  - snapshot.md")
    print("  - debate_instructions.md")
    print("  - chair_prompt.md")
    print("  - replies/README.txt")
    print(f"Bars (5m): {meta.bar_count}, last bar: {meta.last_bar_time}")
    print()
    print("Next: open debate_instructions.md in Cursor and follow the steps (pick models in the UI).")


if __name__ == "__main__":
    main()
