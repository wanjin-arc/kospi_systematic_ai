from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from kospi100_temporal_risk.modeling import (
    _fill_state,
    _matrix,
    add_regime_temporal_features,
    add_stock_temporal_features,
)


def _positions(dates: pd.DatetimeIndex) -> dict[pd.Timestamp, int]:
    return {pd.Timestamp(value): position for position, value in enumerate(dates)}


class Phase5FModelingTests(unittest.TestCase):
    def test_stock_lookbacks_use_exact_sessions_and_are_causal(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=30)
        frame = pd.DataFrame({
            "date": dates,
            "security_id": "A",
            "membership_spell_id": "A:1",
            "rank__x": np.arange(30, dtype=float) / 30.0,
        })
        result, names, audit = add_stock_temporal_features(frame, ("x",), _positions(dates))
        self.assertEqual(len(names), 5)
        self.assertEqual(result["date"].min(), dates[19])
        row = result.loc[result["date"].eq(dates[20])].iloc[0]
        self.assertAlmostEqual(row["stock_delta5__x"], 5.0 / 30.0)
        self.assertAlmostEqual(row["stock_mean20__x"], np.mean(np.arange(1, 21) / 30.0))
        self.assertFalse(audit["future_rows_used"])

        changed = frame.copy()
        changed.loc[changed["date"].eq(dates[29]), "rank__x"] = -999.0
        rerun, _, _ = add_stock_temporal_features(changed, ("x",), _positions(dates))
        past = result.loc[result["date"].lt(dates[29]), names].reset_index(drop=True)
        past_rerun = rerun.loc[rerun["date"].lt(dates[29]), names].reset_index(drop=True)
        pd.testing.assert_frame_equal(past, past_rerun)

    def test_missing_session_and_membership_spell_reset_history(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=50)
        frame = pd.DataFrame({
            "date": dates,
            "security_id": "A",
            "membership_spell_id": ["A:1"] * 25 + ["A:2"] * 25,
            "rank__x": np.linspace(0.0, 1.0, 50),
        })
        result, _, audit = add_stock_temporal_features(frame, ("x",), _positions(dates))
        self.assertEqual(set(result["date"]), {dates[19], dates[20], dates[21], dates[22], dates[23], dates[24], dates[44], dates[45], dates[46], dates[47], dates[48], dates[49]})
        self.assertEqual(audit["temporal_segments"], 2)

        missing = frame.loc[~frame["date"].eq(dates[10])].copy()
        result_missing, _, missing_audit = add_stock_temporal_features(
            missing, ("x",), _positions(dates)
        )
        self.assertNotIn(dates[19], set(result_missing["date"]))
        self.assertGreater(missing_audit["temporal_segments"], 2)

    def test_market_path_uses_only_completed_history(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=25)
        regime = pd.DataFrame({"date": dates, "m": np.arange(25, dtype=float)})
        result, names, audit = add_regime_temporal_features(regime, ("m",), _positions(dates))
        self.assertEqual(names, ("market_level__m", "market_delta5__m", "market_std20__m"))
        self.assertEqual(result["date"].min(), dates[19])
        self.assertEqual(audit["complete_temporal_dates"], 6)

    def test_preprocessing_is_fit_on_train_only(self) -> None:
        train = pd.DataFrame({
            "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
            "a": [1.0, np.nan],
            "b": [2.0, 4.0],
        })
        validation = pd.DataFrame({
            "date": pd.to_datetime(["2019-01-01"]),
            "a": [1000.0],
            "b": [np.nan],
        })
        state = _fill_state(train, ("a", "b"))
        matrix = _matrix(validation, ("a", "b"), state)
        self.assertEqual(state["fit_max_date"], "2018-01-02")
        self.assertEqual(matrix.tolist(), [[1000.0, 3.0]])


if __name__ == "__main__":
    unittest.main()
