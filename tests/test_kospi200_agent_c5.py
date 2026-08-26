from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from kospi200_agent_c5.runner import SEQUENCE_FEATURES, sequence_feature_frame


class AgentC5Tests(unittest.TestCase):
    def _market(self) -> pd.DataFrame:
        rows = []
        for index, day in enumerate(pd.date_range("2020-01-01", periods=30, freq="B")):
            close = 100.0 + index
            rows.append({"date": day.date().isoformat(), "ticker": "005930", "open": close - 0.5,
                         "high": close + 1.0, "low": close - 1.0, "close": close,
                         "volume": 1000 + index, "listed_shares": 1000000})
        return pd.DataFrame(rows)

    def test_contract_is_ohlcv_path_only(self):
        self.assertEqual(len(SEQUENCE_FEATURES), 10)
        self.assertIn("drawdown_20", SEQUENCE_FEATURES)
        self.assertIn("distance_to_low_20", SEQUENCE_FEATURES)
        self.assertIn("return_volatility_20", SEQUENCE_FEATURES)

    def test_future_bar_cannot_change_past_features(self):
        market = self._market()
        first = sequence_feature_frame(market)
        changed = market.copy(); changed.loc[29, ["open", "high", "low", "close", "volume"]] = [1, 500, 1, 400, 999999]
        second = sequence_feature_frame(changed)
        np.testing.assert_allclose(first.loc[:28, list(SEQUENCE_FEATURES)], second.loc[:28, list(SEQUENCE_FEATURES)], equal_nan=True)


if __name__ == "__main__":
    unittest.main()
