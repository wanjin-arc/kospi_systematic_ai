from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from kospi100_backtest.costs import CostBand, CostSchedule
from kospi200_phase5r.labels import attach_reset_safe_labels


def _fixture(rows: int = 30) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], pd.DataFrame, pd.DataFrame]:
    sessions = tuple(pd.bdate_range("2011-01-03", periods=rows).date.astype(str))
    prices = np.linspace(100.0, 130.0, rows)
    market = pd.DataFrame(
        {
            "date": sessions,
            "ticker": "123456",
            "security_id": "KRX_COMMON:123456",
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "mechanical_reset": False,
            "unresolved_action": False,
        }
    )
    index = pd.DataFrame({"date": sessions, "open": np.linspace(200.0, 220.0, rows)})
    membership = pd.DataFrame(
        {"date": sessions, "ticker": "123456", "security_id": "KRX_COMMON:123456"}
    )
    signals = pd.DataFrame(
        {"date": [sessions[0]], "ticker": ["123456"], "security_id": ["KRX_COMMON:123456"]}
    )
    return signals, market, sessions, index, membership


def _schedule(start: date = date(2011, 1, 1), end: date = date(2012, 12, 31)) -> CostSchedule:
    return CostSchedule((CostBand(start, end, Decimal("0.0015"), Decimal("0.0015")),))


class Phase5RLabelTests(unittest.TestCase):
    def _attach(self, *fixture: object, **kwargs: object) -> tuple[pd.DataFrame, dict[str, object]]:
        signals, market, sessions, index, membership = fixture
        return attach_reset_safe_labels(
            signals,
            market,
            sessions,
            index,
            membership,
            kwargs.pop("schedule", _schedule()),
            **kwargs,
        )

    def test_exact_t_plus_1_to_t_plus_21_net_active_and_mae(self) -> None:
        fixture = _fixture()
        labeled, audit = self._attach(*fixture)
        row = labeled.iloc[0]
        self.assertTrue(row["label_valid"])
        self.assertEqual(row["entry_date"], fixture[2][1])
        self.assertEqual(row["exit_date"], fixture[2][21])
        entry = float(fixture[1].iloc[1]["open"])
        exit_ = float(fixture[1].iloc[21]["open"])
        expected_net = (
            exit_ * (1 - 0.001) * (1 - 0.0002 - 0.0015 - 0.0015)
            / (entry * (1 + 0.001) * (1 + 0.0002))
            - 1
        )
        index_return = float(fixture[3].iloc[21]["open"] / fixture[3].iloc[1]["open"] - 1)
        lows = fixture[1].iloc[1:21]["low"].to_numpy(float)
        mae = max(0.0, 1.0 - lows.min() / entry)
        self.assertAlmostEqual(row["target_stock_net_return_20"], expected_net)
        self.assertAlmostEqual(row["target_net_active_20"], expected_net - index_return)
        self.assertAlmostEqual(row["target_mae_20"], mae)
        self.assertAlmostEqual(row["target_quality_20"], expected_net - index_return - 0.5 * mae)
        self.assertEqual(audit["complete_label_rows"], 1)
        self.assertTrue(audit["score_universe_rows_unchanged"])

    def test_reset_or_unresolved_action_anywhere_through_exit_invalidates(self) -> None:
        for flag in ("mechanical_reset", "unresolved_action"):
            fixture = list(_fixture())
            fixture[1] = fixture[1].copy()
            fixture[1].loc[10, flag] = True
            labeled, _ = self._attach(*fixture)
            self.assertFalse(labeled.iloc[0]["label_valid"])
            expected = "RESET_CROSSING" if flag == "mechanical_reset" else "UNRESOLVED_ACTION_CROSSING"
            self.assertIn(expected, labeled.iloc[0]["label_invalid_reason"])
            self.assertTrue(labeled.loc[:, "target_quality_20"].isna().all())

    def test_membership_gap_and_missing_ohlc_are_fail_closed(self) -> None:
        fixture = list(_fixture())
        fixture[4] = fixture[4].drop(index=8)
        fixture[1] = fixture[1].copy()
        fixture[1].loc[12, "low"] = np.nan
        labeled, audit = self._attach(*fixture)
        reasons = labeled.iloc[0]["label_invalid_reason"]
        self.assertIn("MEMBERSHIP_OR_IDENTITY_GAP", reasons)
        self.assertIn("MISSING_REQUIRED_OHLC", reasons)
        self.assertEqual(audit["output_rows"], len(fixture[0]))

    def test_future_gap_limit_changes_label_not_signal_rows(self) -> None:
        fixture = list(_fixture())
        fixture[1] = fixture[1].copy()
        fixture[1].loc[1, ["open", "high", "close"]] = [110.0, 111.0, 110.0]
        fixture[1].loc[1, "low"] = 109.0
        original = fixture[0][["date", "ticker"]].copy()
        labeled, audit = self._attach(*fixture)
        self.assertFalse(labeled.iloc[0]["label_valid"])
        self.assertIn("UNFILLED_GAP_LIMIT", labeled.iloc[0]["label_invalid_reason"])
        pd.testing.assert_frame_equal(original.reset_index(drop=True), labeled[["date", "ticker"]].reset_index(drop=True))
        self.assertFalse(audit["future_label_availability_used_for_scoring"])

    def test_unknown_exit_tax_date_raises_instead_of_guessing(self) -> None:
        fixture = _fixture()
        incomplete = _schedule(date(2011, 1, 1), date(2011, 1, 10))
        with self.assertRaises(KeyError):
            self._attach(*fixture, schedule=incomplete)

    def test_excluded_security_is_rejected_before_labeling(self) -> None:
        fixture = list(_fixture())
        fixture[0] = pd.DataFrame(
            {"date": [fixture[2][0]], "ticker": ["005930"], "security_id": ["KRX_COMMON:005930"]}
        )
        with self.assertRaises(ValueError):
            self._attach(*fixture)

    def test_insufficient_future_history_keeps_score_row_with_invalid_label(self) -> None:
        fixture = list(_fixture())
        fixture[0] = pd.DataFrame(
            {"date": [fixture[2][-2]], "ticker": ["123456"], "security_id": ["KRX_COMMON:123456"]}
        )
        labeled, _ = self._attach(*fixture)
        self.assertEqual(len(labeled), 1)
        self.assertFalse(labeled.iloc[0]["label_valid"])
        self.assertEqual(labeled.iloc[0]["label_invalid_reason"], "INSUFFICIENT_FUTURE_SESSIONS")


if __name__ == "__main__":
    unittest.main()
