from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from kospi200_fundamental import FACTOR_IDS, compute_factors, cross_sectional_transform


class FundamentalFactorTests(unittest.TestCase):
    def test_exactly_twenty_preregistered_factors(self) -> None:
        self.assertEqual(len(FACTOR_IDS), 20)
        self.assertEqual(len(set(FACTOR_IDS)), 20)

    def test_factor_arithmetic_uses_current_and_prior_only(self) -> None:
        current = {
            "assets": 1000, "equity": 400, "liabilities": 600, "current_assets": 300,
            "current_liabilities": 150, "cash_and_equivalents": 100, "revenue": 800,
            "operating_income": 80, "net_income": 40, "operating_cash_flow": 70,
            "capital_expenditure": 20, "market_cap": 2000,
        }
        prior = {"assets": 900, "equity": 350, "revenue": 700, "operating_income": 70, "net_income": 35}
        result = compute_factors(current, prior)
        self.assertAlmostEqual(result["roe"], 0.1)
        self.assertAlmostEqual(result["free_cash_flow_yield"], 0.025)
        self.assertAlmostEqual(result["revenue_growth_yoy"], 800 / 700 - 1)

    def test_zero_denominator_becomes_missing_not_infinite(self) -> None:
        result = compute_factors({"equity": 0, "net_income": 1}, {})
        self.assertTrue(np.isnan(result["roe"]))

    def test_cross_sectional_transform_does_not_fill_missing_values(self) -> None:
        rows = []
        for index in range(6):
            row = {"date": "2020-01-02", "ticker": f"{index:06d}", "sector": "A"}
            row.update({factor: float(index + 1) for factor in FACTOR_IDS})
            rows.append(row)
        rows[0]["roe"] = np.nan
        transformed = cross_sectional_transform(pd.DataFrame(rows))
        self.assertTrue(np.isnan(transformed.loc[0, "roe__percentile"]))

    def test_sector_transform_is_used_only_when_sector_has_five_names(self) -> None:
        rows = []
        # Five names in sector A are eligible for sector-relative ranking.
        for index in range(5):
            row = {"date": "2020-01-02", "ticker": f"A{index}", "sector": "A"}
            row.update({factor: float(index + 1) for factor in FACTOR_IDS})
            rows.append(row)
        # A singleton sector must fall back to the date-wide cross section.
        row = {"date": "2020-01-02", "ticker": "B0", "sector": "B"}
        row.update({factor: 100.0 for factor in FACTOR_IDS})
        rows.append(row)
        transformed = cross_sectional_transform(pd.DataFrame(rows))
        self.assertAlmostEqual(float(transformed.loc[4, "roe__percentile"]), 1.0)
        self.assertAlmostEqual(float(transformed.loc[5, "roe__percentile"]), 1.0)
        # The singleton's robust z is not computed from a one-row sector.
        self.assertTrue(np.isfinite(float(transformed.loc[5, "roe__robust_z"])))


if __name__ == "__main__":
    unittest.main()
