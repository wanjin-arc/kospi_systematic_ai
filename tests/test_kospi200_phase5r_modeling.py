from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from kospi200_phase5r.modeling import (
    AGENT_B_PERCENTILE_COLUMN,
    AGENT_B_PREDICTION_COLUMN,
    AGENT_C_PERCENTILE_COLUMN,
    AGENT_C_PREDICTION_COLUMN,
    AGENT_D_PERCENTILE_COLUMN,
    FUNDAMENTAL_AVAILABLE_COLUMN,
    attach_neutral_agent_b_scores,
    agent_b_feature_columns,
    agent_c_feature_columns,
    build_purged_embargo_fold,
    daily_percentile,
    fit_predict_agent_b,
    fit_predict_agent_c,
    fit_predict_agent_d,
    generate_walk_forward_scores,
    make_agent_b_model,
    make_agent_c_model,
    make_agent_d_model,
    per_date_top_n_metric,
    per_date_top_n_rows,
)


class Phase5RModelingTests(unittest.TestCase):
    def test_feature_contract_has_twenty_fundamental_and_seventeen_technical_columns(self) -> None:
        self.assertEqual(len(agent_b_feature_columns()), 20)
        self.assertTrue(
            all(name.endswith("__phase4e_percentile") for name in agent_b_feature_columns())
        )
        self.assertEqual(len(agent_c_feature_columns()), 17)
        self.assertNotIn("agent_b_percentile", agent_c_feature_columns())

    def test_fixed_model_families_and_parameters(self) -> None:
        b = make_agent_b_model()
        c = make_agent_c_model()
        d = make_agent_d_model()
        self.assertIsInstance(b.named_steps["model"], Ridge)
        self.assertEqual(float(b.named_steps["model"].alpha), 10.0)
        self.assertEqual(b.named_steps["imputer"].strategy, "median")
        self.assertTrue(b.named_steps["imputer"].keep_empty_features)
        self.assertIsInstance(c.named_steps["model"], HistGradientBoostingRegressor)
        self.assertEqual(c.named_steps["model"].max_depth, 3)
        self.assertEqual(c.named_steps["model"].max_iter, 100)
        self.assertEqual(c.named_steps["model"].min_samples_leaf, 100)
        self.assertEqual(c.named_steps["model"].l2_regularization, 10.0)
        self.assertTrue(d.named_steps["model"].positive)
        with self.assertRaisesRegex(ValueError, "고정"):
            make_agent_b_model({"agent_b": {"alpha": 1.0}})
        with self.assertRaisesRegex(ValueError, "고정"):
            make_agent_b_model({"agent_b": {"keep_empty_features": False}})
        with self.assertRaisesRegex(ValueError, "고정"):
            make_agent_b_model({"agent_b": {"all_missing_fold_policy": "DROP"}})
        with self.assertRaisesRegex(ValueError, "hard_fundamental_gate|hard gate"):
            make_agent_d_model({"agent_d": {"hard_fundamental_gate": True}})

    def test_daily_percentile_is_cross_sectional_by_date(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2020-01-02"] * 3 + ["2020-01-03"] * 2,
                "score": [1.0, 2.0, 2.0, 100.0, 200.0],
            }
        )
        result = daily_percentile(frame, "score", "percentile")
        np.testing.assert_allclose(result["percentile"], [1 / 3, 5 / 6, 5 / 6, 0.5, 1.0])

    def test_missing_agent_b_is_neutral_and_never_hard_gates_universe(self) -> None:
        universe = pd.DataFrame(
            {
                "date": ["2020-01-02"] * 3,
                "ticker": ["000001", "000002", "000003"],
                AGENT_C_PERCENTILE_COLUMN: [0.2, 0.8, 0.5],
            },
            index=[8, 3, 5],
        )
        b = pd.DataFrame(
            {
                "date": ["2020-01-02", "2020-01-02"],
                "ticker": ["000001", "000003"],
                AGENT_B_PREDICTION_COLUMN: [-0.1, 0.2],
                AGENT_B_PERCENTILE_COLUMN: [0.5, 1.0],
            }
        )
        result = attach_neutral_agent_b_scores(universe, b)
        self.assertEqual(result["ticker"].tolist(), universe["ticker"].tolist())
        self.assertEqual(result.index.tolist(), universe.index.tolist())
        self.assertEqual(len(result), len(universe))
        missing = result.loc[result["ticker"].eq("000002")].iloc[0]
        self.assertEqual(float(missing[AGENT_B_PERCENTILE_COLUMN]), 0.5)
        self.assertEqual(int(missing[FUNDAMENTAL_AVAILABLE_COLUMN]), 0)
        self.assertEqual(
            result[FUNDAMENTAL_AVAILABLE_COLUMN].tolist(),
            [1, 0, 1],
        )

    @staticmethod
    def _regression_frames(rows: int = 240) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = np.random.default_rng(20260831)
        x1 = rng.normal(size=rows)
        x2 = rng.normal(size=rows)
        dates = pd.date_range("2017-01-02", periods=rows // 4, freq="B").repeat(4)
        tickers = [f"{value:06d}" for value in np.tile(np.arange(4), rows // 4)]
        target = 0.4 * x1 - 0.2 * x2 + rng.normal(scale=0.02, size=rows)
        train = pd.DataFrame(
            {
                "date": dates.astype(str),
                "ticker": tickers,
                "f1": x1,
                "f2": x2,
                "target_quality_20": target,
                "label_valid": True,
            }
        )
        score = train.iloc[-12:].drop(columns=["target_quality_20", "label_valid"]).copy()
        return train.iloc[:-12].copy(), score

    def test_agent_b_and_c_emit_fixed_columns_and_serializable_audit(self) -> None:
        train, score = self._regression_frames()
        b_scored, b_fit = fit_predict_agent_b(train, score, ["f1", "f2"])
        c_scored, c_fit = fit_predict_agent_c(train, score, ["f1", "f2"])
        self.assertIn(AGENT_B_PREDICTION_COLUMN, b_scored)
        self.assertIn(AGENT_B_PERCENTILE_COLUMN, b_scored)
        self.assertIn(AGENT_C_PREDICTION_COLUMN, c_scored)
        self.assertIn(AGENT_C_PERCENTILE_COLUMN, c_scored)
        json.dumps(b_fit.audit, allow_nan=False)
        json.dumps(c_fit.audit, allow_nan=False)
        self.assertEqual(b_fit.audit["fixed_parameters"]["alpha"], 10.0)
        self.assertEqual(c_fit.audit["fixed_parameters"]["max_depth"], 3)
        self.assertEqual(len(b_scored), len(score))
        self.assertEqual(len(c_scored), len(score))

    def test_agent_b_keeps_twenty_columns_when_fold_features_are_all_missing(self) -> None:
        rng = np.random.default_rng(20260901)
        features = agent_b_feature_columns()
        rows = 80
        train = pd.DataFrame(
            {
                "date": pd.date_range("2017-01-02", periods=rows, freq="B").astype(str),
                "ticker": [f"{value % 10:06d}" for value in range(rows)],
                "target_quality_20": rng.normal(size=rows),
                "label_valid": True,
            }
        )
        score = train.iloc[-10:][["date", "ticker"]].copy()
        all_missing = features[-5:]
        for feature in features:
            train[feature] = np.nan if feature in all_missing else rng.normal(size=rows)
            score[feature] = (
                rng.normal(size=len(score)) if feature in all_missing else rng.normal(size=len(score))
            )

        scored, fitted = fit_predict_agent_b(train, score, features)

        self.assertEqual(fitted.model.n_features_in_, 20)
        self.assertEqual(fitted.model.named_steps["imputer"].n_features_in_, 20)
        self.assertEqual(fitted.model.named_steps["scale"].n_features_in_, 20)
        self.assertEqual(fitted.model.named_steps["model"].n_features_in_, 20)
        imputed_score = fitted.model.named_steps["imputer"].transform(score.loc[:, features])
        self.assertEqual(imputed_score.shape, (len(score), 20))
        self.assertTrue(np.isfinite(imputed_score).all())
        self.assertTrue(np.isfinite(scored[AGENT_B_PREDICTION_COLUMN]).all())
        coefficient = np.asarray(fitted.model.named_steps["model"].coef_, dtype=float)
        np.testing.assert_allclose(coefficient[-5:], 0.0, atol=1e-12)
        self.assertEqual(fitted.audit["feature_columns"], list(features))
        self.assertEqual(
            fitted.audit["fixed_parameters"]["all_missing_fold_policy"],
            "KEEP_FEATURE_ZERO_AFTER_IMPUTE",
        )

    def test_agent_c_and_d_still_reject_all_missing_features(self) -> None:
        train, score = self._regression_frames()
        train["f2"] = np.nan
        score["f2"] = np.nan
        with self.assertRaisesRegex(ValueError, "전부 결측"):
            fit_predict_agent_c(train, score, ["f1", "f2"])

        rows = 12
        d_train = pd.DataFrame(
            {
                "date": pd.date_range("2017-01-02", periods=rows, freq="B").astype(str),
                "ticker": [f"{value:06d}" for value in range(rows)],
                AGENT_B_PERCENTILE_COLUMN: np.nan,
                AGENT_C_PERCENTILE_COLUMN: np.linspace(0.1, 0.9, rows),
                FUNDAMENTAL_AVAILABLE_COLUMN: 1,
                "target_quality_20": np.linspace(-0.1, 0.1, rows),
                "is_oof": True,
            }
        )
        d_score = d_train.iloc[-4:].drop(columns=["target_quality_20", "is_oof"])
        with self.assertRaisesRegex(ValueError, "결측"):
            fit_predict_agent_d(d_train, d_score)

    def test_agent_d_requires_oof_and_has_nonnegative_coefficients(self) -> None:
        rows = 80
        b = np.tile([0.25, 0.5, 0.75, 1.0], rows // 4)
        c = np.tile([1.0, 0.75, 0.5, 0.25], rows // 4)
        available = np.tile([1, 0, 1, 1], rows // 4)
        b = np.where(available == 0, 0.5, b)
        train = pd.DataFrame(
            {
                "date": pd.date_range("2017-01-02", periods=rows, freq="B").astype(str),
                "ticker": [f"{value % 20:06d}" for value in range(rows)],
                AGENT_B_PERCENTILE_COLUMN: b,
                AGENT_C_PERCENTILE_COLUMN: c,
                FUNDAMENTAL_AVAILABLE_COLUMN: available,
                "target_quality_20": 0.6 * b + 0.3 * c + 0.05 * available,
                "is_oof": True,
            }
        )
        score = train.iloc[-8:].drop(columns=["target_quality_20", "is_oof"]).copy()
        invalid = train.copy()
        invalid.loc[0, "is_oof"] = False
        with self.assertRaisesRegex(ValueError, "OOF"):
            fit_predict_agent_d(invalid, score)

        scored, fitted = fit_predict_agent_d(train, score)
        self.assertEqual(len(scored), len(score))
        self.assertIn(AGENT_D_PERCENTILE_COLUMN, scored)
        coefficient = np.asarray(fitted.model.named_steps["model"].coef_, dtype=float)
        self.assertTrue((coefficient >= -1e-12).all())
        self.assertTrue(fitted.audit["oof_only"])
        self.assertFalse(fitted.audit["hard_fundamental_gate"])

    def test_top_n_metric_selects_n_inside_each_date(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2020-01-02"] * 3 + ["2020-01-03"] * 3,
                "ticker": ["A", "B", "C", "A", "B", "C"],
                "score": [100.0, 90.0, 80.0, 3.0, 2.0, 1.0],
                "metric": [10.0, 8.0, 0.0, 6.0, 4.0, 0.0],
            }
        )
        selected = per_date_top_n_rows(frame, "score", 2)
        self.assertEqual(selected.groupby("date").size().to_dict(), {"2020-01-02": 2, "2020-01-03": 2})
        self.assertEqual(per_date_top_n_metric(frame, "score", "metric", 2), 7.0)

    def test_anchored_fold_applies_single_purge_without_pre_fold_embargo(self) -> None:
        sessions = [f"S{value:02d}" for value in range(15)]
        frame = pd.DataFrame({"date": sessions, "value": range(15)})
        fold = build_purged_embargo_fold(
            frame,
            sessions,
            "S10",
            "S12",
            purge_sessions=2,
            embargo_sessions=2,
        )
        self.assertEqual(fold.train_dates, tuple(sessions[:8]))
        self.assertEqual(fold.purged_dates, ("S08", "S09"))
        self.assertEqual(fold.embargoed_dates, ())
        self.assertEqual(int(fold.train_mask.sum()), 8)
        self.assertEqual(int(fold.evaluation_mask.sum()), 3)

    def test_embargo_only_removes_post_evaluation_rows_that_reenter_training(self) -> None:
        sessions = [f"S{value:02d}" for value in range(18)]
        frame = pd.DataFrame({"date": sessions})
        candidate = [*sessions[:10], *sessions[13:]]
        fold = build_purged_embargo_fold(
            frame,
            sessions,
            "S10",
            "S12",
            purge_sessions=2,
            embargo_sessions=2,
            candidate_training_dates=candidate,
        )
        self.assertEqual(fold.purged_dates, ("S08", "S09"))
        self.assertEqual(fold.embargoed_dates, ("S13", "S14"))
        self.assertIn("S15", fold.train_dates)
        self.assertNotIn("S13", fold.train_dates)
        self.assertEqual(int(fold.embargoed_mask.sum()), 2)
        json.dumps(fold.audit, allow_nan=False)

    def test_generate_walk_forward_scores_builds_inner_oof_soft_fusion(self) -> None:
        b_features = agent_b_feature_columns()
        c_features = agent_c_feature_columns()
        sessions: list[str] = []
        for year in range(2015, 2020):
            sessions.extend(
                pd.date_range(f"{year}-01-02", periods=30, freq="B").date.astype(str).tolist()
            )
        rows: list[dict[str, object]] = []
        for day_index, day in enumerate(sessions):
            for ticker_index in range(4):
                available = int(ticker_index != 1)
                row: dict[str, object] = {
                    "date": day,
                    "ticker": f"{ticker_index + 1:06d}",
                    "fundamental_available": available,
                    "target_quality_20": 0.01 * ticker_index + 0.0001 * day_index,
                    "label_valid": True,
                }
                for feature_index, name in enumerate(b_features):
                    row[name] = (
                        ((ticker_index + feature_index + day_index) % 17) / 16
                        if available
                        else np.nan
                    )
                for feature_index, name in enumerate(c_features):
                    row[name] = np.sin((day_index + 1) * (feature_index + 1) / 50) + ticker_index
                rows.append(row)
        panel = pd.DataFrame(rows)
        config = {
            "outer_evaluation_years": [2019],
            "inner_oof_start_year": 2018,
            "purge_sessions": 20,
            "embargo_sessions": 20,
            "seed": 20260831,
            "agent_b": {"model": "RIDGE_FIXED", "alpha": 10.0},
            "agent_c": {
                "model": "HIST_GRADIENT_BOOSTING_FIXED",
                "learning_rate": 0.05,
                "max_depth": 3,
                "max_iter": 100,
                "min_samples_leaf": 100,
                "l2_regularization": 10.0,
            },
            "agent_d": {
                "model": "POSITIVE_RIDGE_OOF",
                "alpha": 10.0,
                "hard_fundamental_gate": False,
            },
            "portfolio": {"alpha_size": 10},
        }
        config_object = SimpleNamespace(payload=config, seed=20260831)
        scores, metrics, state = generate_walk_forward_scores(panel, sessions, config_object)
        required = {
            "date",
            "ticker",
            "target_quality_20",
            "agent_b_prediction",
            "agent_b_percentile",
            "agent_c_prediction",
            "agent_c_percentile",
            "fundamental_available",
            "agent_d_prediction",
            "agent_d_percentile",
            "outer_year",
        }
        self.assertTrue(required.issubset(scores.columns))
        self.assertEqual(set(scores["outer_year"]), {2019})
        self.assertEqual(len(scores), 30 * 4)
        missing_b = scores["fundamental_available"].eq(0)
        self.assertTrue(scores.loc[missing_b, "agent_b_percentile"].eq(0.5).all())
        self.assertTrue(scores.loc[missing_b, "agent_b_prediction"].isna().all())
        self.assertEqual(set(metrics["agent"]), {"B_ONLY", "C_ONLY", "D_SOFT_FUSION"})
        self.assertEqual(metrics["embargoed_dates"].tolist(), [0, 0, 0])
        self.assertTrue(state["oof_only_fusion"])
        self.assertFalse(state["hard_fundamental_gate"])
        self.assertIn("2019", state["outer_models"])
        json.dumps(state["outer_audit"], allow_nan=False)


if __name__ == "__main__":
    unittest.main()
