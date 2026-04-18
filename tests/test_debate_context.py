import unittest

import pandas as pd

from debate.context import build_market_snapshot, synthetic_ohlcv_for_tests
from mnq_data import add_indicators, compute_signals_5m


class DebateContextTests(unittest.TestCase):
    def test_snapshot_non_empty_from_synthetic(self):
        df = synthetic_ohlcv_for_tests(60)
        df = add_indicators(df)
        sig = compute_signals_5m(df)
        md, meta = build_market_snapshot(
            symbol="TEST", df_5m=df, df_1m=None, signals_5m=sig
        )
        self.assertIn("# MNQ market snapshot", md)
        self.assertIn("TEST", md)
        self.assertGreater(meta.bar_count, 0)

    def test_snapshot_no_data(self):
        empty = pd.DataFrame()
        md, meta = build_market_snapshot(symbol="X", df_5m=empty)
        self.assertIn("No data", md)
        self.assertEqual(meta.bar_count, 0)


if __name__ == "__main__":
    unittest.main()
