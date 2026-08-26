from __future__ import annotations

import unittest

import pandas as pd

from kospi200_agent_b4.runner import add_temporal_features, feature_columns
from kospi200_fundamental import FACTOR_IDS


class AgentB4Tests(unittest.TestCase):
    def test_feature_contract_has_market_sector_and_temporal_views(self):
        columns = feature_columns()
        self.assertEqual(len(columns), 121)
        self.assertIn("roe__market_percentile", columns)
        self.assertIn("roe__robust_z", columns)
        self.assertIn("roe__sector_z_delta_1m", columns)
        self.assertIn("roe__sector_z_delta_3m", columns)

    def test_temporal_deltas_use_only_prior_months(self):
        rows = []
        for month, value in enumerate((1.0, 2.0, 5.0, 9.0), 1):
            row = {"date": f"2020-0{month}-28", "ticker": "005930"}
            for factor in FACTOR_IDS:
                row[f"{factor}__robust_z"] = value
            rows.append(row)
        result = add_temporal_features(pd.DataFrame(rows))
        self.assertEqual(result.loc[3, "roe__sector_z_delta_1m"], 4.0)
        self.assertEqual(result.loc[3, "roe__sector_z_delta_3m"], 8.0)


if __name__ == "__main__":
    unittest.main()
