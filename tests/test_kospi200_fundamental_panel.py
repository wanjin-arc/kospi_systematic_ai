from __future__ import annotations

import unittest

from kospi200_fundamental.panel import fiscal_key, trailing_values


class FundamentalPanelTests(unittest.TestCase):
    def test_report_order_is_quarterly_not_receipt_order(self) -> None:
        self.assertLess(fiscal_key(2020, "11014"), fiscal_key(2020, "11011"))
        self.assertLess(fiscal_key(2020, "11011"), fiscal_key(2021, "11013"))

    def test_interim_ttm_uses_prior_annual_plus_current_minus_prior_same_period(self) -> None:
        statements = {
            (2019, 4): {"revenue": 100.0},
            (2019, 1): {"revenue": 20.0},
            (2020, 1): {"revenue": 30.0, "assets": 200.0},
        }
        result = trailing_values(statements, 2020, 1)
        self.assertEqual(result["revenue"], 110.0)
        self.assertEqual(result["assets"], 200.0)

    def test_missing_ttm_dependency_stays_missing(self) -> None:
        result = trailing_values({(2020, 2): {"revenue": 60.0}}, 2020, 2)
        self.assertIsNone(result["revenue"])


if __name__ == "__main__":
    unittest.main()
