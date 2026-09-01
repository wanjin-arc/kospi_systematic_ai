from __future__ import annotations

from dataclasses import replace
import pickle
from unittest.mock import patch
import unittest

import numpy as np
import pandas as pd

from kospi200_phase4e.modeling import (
    FREEZE_DATE,
    PRIMARY_B,
    PRIMARY_C,
    PRIMARY_D,
    bundle_state_hashes,
    fit_frozen_model_bundle,
    predict_frozen_bundle,
    select_primary_agent,
    validate_fit_boundary,
)
from kospi200_phase5r.modeling import agent_b_feature_columns, agent_c_feature_columns


def _panel() -> tuple[pd.DataFrame, list[str]]:
    sessions: list[str] = []
    for year in range(2015, 2022):
        sessions.extend(
            pd.date_range(f"{year}-01-02", periods=30, freq="B").date.astype(str).tolist()
        )
    b_features = agent_b_feature_columns()
    c_features = agent_c_feature_columns()
    rows: list[dict[str, object]] = []
    for session_number, day in enumerate(sessions):
        exit_number = min(session_number + 21, len(sessions) - 1)
        exit_day = sessions[exit_number]
        for ticker_number in range(6):
            available = int(ticker_number != 1)
            row: dict[str, object] = {
                "date": day,
                "ticker": f"{ticker_number + 1:06d}",
                "exit_date": exit_day,
                "label_valid": session_number + 21 < len(sessions),
                "target_quality_20": (
                    0.02 * ticker_number
                    + 0.0001 * session_number
                    + 0.01 * np.sin(session_number / 7)
                ),
                "fundamental_available": available,
            }
            for feature_number, name in enumerate(b_features):
                row[name] = (
                    ((ticker_number + feature_number + session_number) % 19) / 18
                    if available
                    else np.nan
                )
            for feature_number, name in enumerate(c_features):
                row[name] = ticker_number + np.sin(
                    (session_number + 1) * (feature_number + 1) / 60
                )
            rows.append(row)
    return pd.DataFrame(rows), sessions


class Phase4EModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel, cls.sessions = _panel()
        cls.bundle = fit_frozen_model_bundle(cls.panel, cls.sessions)

    def test_bundle_is_picklable_and_contains_real_models_and_feature_order(self) -> None:
        restored = pickle.loads(pickle.dumps(self.bundle))
        self.assertIn(restored.primary_agent, {PRIMARY_B, PRIMARY_C, PRIMARY_D})
        self.assertEqual(restored.agent_b_features, agent_b_feature_columns())
        self.assertEqual(restored.agent_c_features, agent_c_feature_columns())
        self.assertEqual(restored.agent_d_features, (
            "agent_b_percentile", "agent_c_percentile", "fundamental_available"
        ))
        self.assertTrue(hasattr(restored.agent_b_estimator, "predict"))
        self.assertTrue(hasattr(restored.agent_c_estimator, "predict"))
        self.assertTrue(hasattr(restored.agent_d_estimator, "predict"))
        self.assertEqual(restored.audit["selection_years"], [2019, 2020])
        self.assertEqual(restored.audit["oof_roles"]["d_meta_training"], [2017, 2018])
        self.assertFalse(restored.audit["selection_uses_portfolio_metrics"])
        self.assertTrue(restored.selection_oof_scores)
        self.assertEqual(
            len(restored.selection_oof_scores),
            restored.audit["selection_oof_score_rows"],
        )

    def test_same_synthetic_inputs_produce_byte_identical_bundle(self) -> None:
        reproduced = fit_frozen_model_bundle(self.panel, self.sessions)
        self.assertEqual(
            pickle.dumps(self.bundle, protocol=5),
            pickle.dumps(reproduced, protocol=5),
        )

    def test_final_fit_never_contains_2021_or_incomplete_labels(self) -> None:
        boundary = self.bundle.audit["final_fit_boundary"]
        self.assertLessEqual(boundary["signal_max"], FREEZE_DATE)
        self.assertLessEqual(boundary["exit_max"], FREEZE_DATE)
        self.assertGreater(int((self.panel["date"] >= "2021-01-01").sum()), 0)
        bad = self.panel.loc[
            (self.panel["date"] >= "2021-01-01") & self.panel["label_valid"]
        ].copy()
        with self.assertRaisesRegex(ValueError, "2020-12-30 이후"):
            validate_fit_boundary(bad)

    def test_d_must_strictly_improve_best_single_agent(self) -> None:
        base = pd.DataFrame(
            [
                {"agent": PRIMARY_B, "mean_rank_ic": 0.04, "nonnegative_years": 2, "mean_top10_target_quality": 0.03, "evaluated_years": 2},
                {"agent": PRIMARY_C, "mean_rank_ic": 0.03, "nonnegative_years": 2, "mean_top10_target_quality": 0.02, "evaluated_years": 2},
                {"agent": PRIMARY_D, "mean_rank_ic": 0.035, "nonnegative_years": 2, "mean_top10_target_quality": 0.03, "evaluated_years": 2},
            ]
        )
        self.assertEqual(select_primary_agent(base), PRIMARY_B)

        improved = base.copy()
        improved.loc[improved["agent"].eq(PRIMARY_D), "mean_rank_ic"] = 0.041
        self.assertEqual(select_primary_agent(improved), PRIMARY_D)

        tied = improved.copy()
        tied.loc[tied["agent"].eq(PRIMARY_D), "mean_rank_ic"] = 0.04
        self.assertEqual(select_primary_agent(tied), PRIMARY_B)

        incomplete = improved.copy()
        incomplete.loc[incomplete["agent"].eq(PRIMARY_D), "evaluated_years"] = 1
        self.assertEqual(select_primary_agent(incomplete), PRIMARY_B)

        worse_top10 = improved.copy()
        worse_top10.loc[
            worse_top10["agent"].eq(PRIMARY_D), "mean_top10_target_quality"
        ] = 0.029
        self.assertEqual(select_primary_agent(worse_top10), PRIMARY_B)

    def test_single_agent_order_uses_stability_then_top10_and_c_tie_break(self) -> None:
        metrics = pd.DataFrame(
            [
                {"agent": PRIMARY_B, "mean_rank_ic": 0.04, "nonnegative_years": 1, "mean_top10_target_quality": 0.10, "evaluated_years": 2},
                {"agent": PRIMARY_C, "mean_rank_ic": 0.04, "nonnegative_years": 2, "mean_top10_target_quality": 0.01, "evaluated_years": 2},
                {"agent": PRIMARY_D, "mean_rank_ic": 0.03, "nonnegative_years": 2, "mean_top10_target_quality": 0.10, "evaluated_years": 2},
            ]
        )
        self.assertEqual(select_primary_agent(metrics), PRIMARY_C)
        metrics.loc[metrics["agent"].eq(PRIMARY_B), "nonnegative_years"] = 2
        metrics.loc[metrics["agent"].eq(PRIMARY_B), "mean_top10_target_quality"] = 0.01
        self.assertEqual(select_primary_agent(metrics), PRIMARY_C)

    def test_label_validity_does_not_change_current_oof_score_universe(self) -> None:
        target_day = self.panel.loc[self.panel["date"].str.startswith("2020-") , "date"].min()
        changed = self.panel.copy()
        changed.loc[
            changed["date"].eq(target_day) & changed["ticker"].eq("000006"),
            "label_valid",
        ] = False
        changed_bundle = fit_frozen_model_bundle(changed, self.sessions)

        base_scores = pd.DataFrame(self.bundle.selection_oof_scores)
        changed_scores = pd.DataFrame(changed_bundle.selection_oof_scores)
        columns = [
            "ticker",
            "agent_b_percentile",
            "agent_c_percentile",
            "agent_d_percentile",
        ]
        base_day = base_scores.loc[base_scores["date"].eq(target_day), columns].sort_values("ticker")
        changed_day = changed_scores.loc[
            changed_scores["date"].eq(target_day), columns
        ].sort_values("ticker")
        self.assertEqual(len(base_day), 6)
        self.assertEqual(len(changed_day), 6)
        pd.testing.assert_frame_equal(
            base_day.reset_index(drop=True),
            changed_day.reset_index(drop=True),
        )
        retained = changed_scores.loc[
            changed_scores["date"].eq(target_day)
            & changed_scores["ticker"].eq("000006")
        ].iloc[0]
        self.assertFalse(bool(retained["label_valid"]))

    def test_bundle_state_hashes_cover_components_and_selection_contract(self) -> None:
        hashes = bundle_state_hashes(self.bundle)
        self.assertEqual(
            set(hashes["component_sha256"]),
            {"agent_b", "agent_c", "agent_d"},
        )
        self.assertTrue(all(len(value) == 64 for value in hashes["component_sha256"].values()))
        self.assertEqual(len(hashes["model_state_hash"]), 64)
        reproduced = fit_frozen_model_bundle(self.panel, self.sessions)
        self.assertEqual(hashes, bundle_state_hashes(reproduced))
        changed_primary = replace(
            self.bundle,
            primary_agent=PRIMARY_B if self.bundle.primary_agent != PRIMARY_B else PRIMARY_C,
        )
        changed_hashes = bundle_state_hashes(changed_primary)
        self.assertEqual(hashes["component_sha256"], changed_hashes["component_sha256"])
        self.assertNotEqual(hashes["model_state_hash"], changed_hashes["model_state_hash"])

    def test_predict_only_api_never_calls_fit(self) -> None:
        score = self.panel.loc[self.panel["date"] >= "2021-01-01"].copy()
        score = score.drop(columns=["exit_date", "label_valid", "target_quality_20"])
        estimators = (
            self.bundle.agent_b_estimator,
            self.bundle.agent_c_estimator,
            self.bundle.agent_d_estimator,
        )
        with (
            patch.object(estimators[0], "fit", side_effect=AssertionError("B fit called")) as b_fit,
            patch.object(estimators[1], "fit", side_effect=AssertionError("C fit called")) as c_fit,
            patch.object(estimators[2], "fit", side_effect=AssertionError("D fit called")) as d_fit,
        ):
            predicted = predict_frozen_bundle(self.bundle, score)
        b_fit.assert_not_called()
        c_fit.assert_not_called()
        d_fit.assert_not_called()
        self.assertEqual(len(predicted), len(score))
        self.assertTrue(
            {"agent_b_percentile", "agent_c_percentile", "agent_d_percentile", "primary_percentile"}
            .issubset(predicted.columns)
        )

    def test_selected_primary_only_prediction_skips_unneeded_controls(self) -> None:
        score = self.panel.loc[self.panel["date"] >= "2021-01-01"].copy()
        score = score.drop(columns=["exit_date", "label_valid", "target_quality_20"])

        b_bundle = replace(self.bundle, primary_agent=PRIMARY_B)
        with (
            patch.object(b_bundle.agent_c_estimator, "predict", side_effect=AssertionError("C called")) as c_predict,
            patch.object(b_bundle.agent_d_estimator, "predict", side_effect=AssertionError("D called")) as d_predict,
        ):
            b_scores = predict_frozen_bundle(b_bundle, score, include_controls=False)
        c_predict.assert_not_called()
        d_predict.assert_not_called()
        self.assertIn("agent_b_percentile", b_scores)
        self.assertNotIn("agent_c_percentile", b_scores)
        self.assertNotIn("agent_d_percentile", b_scores)

        c_bundle = replace(self.bundle, primary_agent=PRIMARY_C)
        with (
            patch.object(c_bundle.agent_b_estimator, "predict", side_effect=AssertionError("B called")) as b_predict,
            patch.object(c_bundle.agent_d_estimator, "predict", side_effect=AssertionError("D called")) as d_predict,
        ):
            c_scores = predict_frozen_bundle(c_bundle, score, include_controls=False)
        b_predict.assert_not_called()
        d_predict.assert_not_called()
        self.assertIn("agent_c_percentile", c_scores)
        self.assertNotIn("agent_b_percentile", c_scores)
        self.assertNotIn("agent_d_percentile", c_scores)

        d_bundle = replace(self.bundle, primary_agent=PRIMARY_D)
        d_scores = predict_frozen_bundle(d_bundle, score, include_controls=False)
        self.assertTrue(
            {"agent_b_percentile", "agent_c_percentile", "agent_d_percentile"}.issubset(
                d_scores.columns
            )
        )

    def test_selected_primary_only_prediction_never_calls_fit(self) -> None:
        score = self.panel.loc[self.panel["date"] >= "2021-01-01"].copy()
        score = score.drop(columns=["exit_date", "label_valid", "target_quality_20"])
        d_bundle = replace(self.bundle, primary_agent=PRIMARY_D)
        estimators = (
            d_bundle.agent_b_estimator,
            d_bundle.agent_c_estimator,
            d_bundle.agent_d_estimator,
        )
        with (
            patch.object(estimators[0], "fit", side_effect=AssertionError("B fit called")) as b_fit,
            patch.object(estimators[1], "fit", side_effect=AssertionError("C fit called")) as c_fit,
            patch.object(estimators[2], "fit", side_effect=AssertionError("D fit called")) as d_fit,
        ):
            predicted = predict_frozen_bundle(d_bundle, score, include_controls=False)
        b_fit.assert_not_called()
        c_fit.assert_not_called()
        d_fit.assert_not_called()
        self.assertEqual(len(predicted), len(score))


if __name__ == "__main__":
    unittest.main()
