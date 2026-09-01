import unittest

import pandas as pd

from kospi200_phase5r.benchmarks import (
    BenchmarkContractError,
    benchmark_decomposition,
    calendar_year_active_returns,
    comparison_metrics,
    downside_capture,
    ex2_cap_proxy,
    ex2_share_reset_sensitivities,
    exposure_matched_krx1028,
    official_index_returns,
    rolling_active_returns,
)


class Phase5RBenchmarkTests(unittest.TestCase):
    def test_ex2_cap_uses_previous_cap_and_excludes_two_large_names(self):
        dates = ["2023-01-02", "2023-01-03", "2023-01-04"]
        tickers = ["000001", "000002", "005930", "000660"]
        membership = pd.DataFrame(
            [{"date": day, "ticker": ticker} for day in dates for ticker in tickers]
        )
        rows = []
        closes = {
            "000001": [100, 110, 121],
            "000002": [100, 100, 100],
            "005930": [100, 200, 400],
            "000660": [100, 300, 900],
        }
        for date_index, day in enumerate(dates):
            for ticker in tickers:
                cap = 80 if ticker == "000001" else 20 if ticker == "000002" else 10000
                if date_index > 0 and ticker == "000001":
                    cap = 1  # current-day cap must not change the same-day weight
                rows.append({"date": day, "ticker": ticker, "close": closes[ticker][date_index], "market_cap": cap})
        proxy = ex2_cap_proxy(pd.DataFrame(rows), membership)
        self.assertEqual(proxy["benchmark"].unique().tolist(), ["EX2_CAP"])
        self.assertAlmostEqual(proxy.iloc[1]["daily_return"], 0.08)
        # Day 2 caps are A=1, B=20, therefore the next return uses 1/21 * 10%.
        self.assertAlmostEqual(proxy.iloc[2]["daily_return"], 0.1 / 21.0)
        self.assertTrue((proxy["constituent_count"] == 2).all())

    def test_unresolved_share_reset_is_kept_in_two_sensitivities_and_invalidates_gate(self):
        membership = pd.DataFrame(
            {
                "date": ["2021-01-14", "2021-01-14", "2021-01-15", "2021-01-15"],
                "ticker": ["020560", "111111", "020560", "111111"],
            }
        )
        market = pd.DataFrame(
            [
                {"date": "2021-01-14", "ticker": "020560", "close": 4210.0, "listed_shares": 223235294.0, "market_cap": 939820587740.0},
                {"date": "2021-01-14", "ticker": "111111", "close": 100.0, "listed_shares": 9398205877.4, "market_cap": 939820587740.0},
                {"date": "2021-01-15", "ticker": "020560", "close": 18000.0, "listed_shares": 74411764.0, "market_cap": 1339411752000.0},
                {"date": "2021-01-15", "ticker": "111111", "close": 100.0, "listed_shares": 9398205877.4, "market_cap": 939820587740.0},
            ]
        )
        price_unit, issuer_value, audit = ex2_share_reset_sensitivities(
            market,
            membership,
        )
        expected_price = ((18000.0 / 4210.0 - 1.0) * 0.5)
        expected_issuer = ((1339411752000.0 / 939820587740.0 - 1.0) * 0.5)
        self.assertAlmostEqual(price_unit.iloc[1]["daily_return"], expected_price)
        self.assertAlmostEqual(issuer_value.iloc[1]["daily_return"], expected_issuer)
        self.assertEqual(price_unit.iloc[1]["constituent_count"], 2)
        self.assertEqual(issuer_value.iloc[1]["constituent_count"], 2)
        self.assertEqual(audit["ambiguous_event_count"], 1)
        self.assertFalse(audit["resolved_action_contract_complete"])
        self.assertFalse(audit["stable_identity_contract_complete"])
        self.assertFalse(audit["canonical_ex2_return_evaluable"])
        self.assertFalse(audit["sensitivities_are_return_bounds"])

    def test_inverse_price_share_change_is_not_promoted_to_canonical_ex2(self):
        membership = pd.DataFrame(
            {
                "date": ["2021-04-14", "2021-04-15"],
                "ticker": ["035720", "035720"],
            }
        )
        market = pd.DataFrame(
            {
                "date": ["2021-04-14", "2021-04-15"],
                "ticker": ["035720", "035720"],
                "close": [558000.0, 120500.0],
                "market_cap": [49540998438000.0, 53479021252500.0],
                "listed_shares": [88761861.0, 443809305.0],
            }
        )
        with self.assertRaisesRegex(BenchmarkContractError, "canonical EX2"):
            ex2_cap_proxy(market, membership)

    def test_official_and_exposure_matched_returns(self):
        official = official_index_returns(pd.DataFrame({
            "date": ["2023-01-02", "2023-01-03", "2023-01-04"],
            "close": [100.0, 110.0, 99.0],
        }))
        exposure = pd.DataFrame({
            "date": official["date"],
            "stock_exposure": [0.9, 0.5, 0.8],
        })
        matched = exposure_matched_krx1028(official, exposure)
        self.assertAlmostEqual(matched.iloc[1]["daily_return"], 0.05)
        self.assertAlmostEqual(matched.iloc[2]["daily_return"], -0.08)
        self.assertEqual(matched.iloc[-1]["benchmark"], "EXPOSURE_MATCHED_KRX1028")

    def test_rolling_calendar_and_downside_metrics_are_compounded(self):
        strategy = pd.DataFrame({
            "date": ["2022-12-30", "2023-01-02", "2023-01-03", "2023-01-04"],
            "daily_return": [0.10, 0.05, -0.05, 0.02],
        })
        benchmark = pd.DataFrame({
            "date": strategy["date"],
            "daily_return": [0.05, 0.02, -0.10, 0.01],
        })
        rolling = rolling_active_returns(strategy, benchmark, window=3)
        expected_strategy = (1.05 * 0.95 * 1.02) - 1
        expected_benchmark = (1.02 * 0.90 * 1.01) - 1
        self.assertAlmostEqual(rolling.iloc[-1]["active_return"], expected_strategy - expected_benchmark)
        calendar = calendar_year_active_returns(strategy, benchmark)
        self.assertEqual(calendar["year"].tolist(), [2022, 2023])
        self.assertAlmostEqual(downside_capture(strategy, benchmark), 0.5)
        metrics = comparison_metrics(strategy, benchmark, rolling_window=3)
        self.assertAlmostEqual(metrics["worst_rolling_active_return"], rolling["active_return"].min())
        self.assertIn("worst_calendar_active_return", metrics)
        self.assertIn("strategy_mdd", metrics)

    def test_decomposition_reports_all_four_required_differences(self):
        dates = ["2023-01-02", "2023-01-03"]
        def frame(value):
            return pd.DataFrame({"date": dates, "daily_return": [0.0, value]})
        result = benchmark_decomposition(frame(0.04), frame(0.03), frame(0.02), frame(0.01))
        self.assertAlmostEqual(result["phase5r_minus_neutral_core"], 0.01)
        self.assertAlmostEqual(result["ex2_cap_minus_krx1028_full"], 0.01)
        self.assertAlmostEqual(result["neutral_core_minus_ex2_cap"], 0.01)
        self.assertAlmostEqual(result["phase5r_minus_krx1028_full"], 0.03)


if __name__ == "__main__":
    unittest.main()
