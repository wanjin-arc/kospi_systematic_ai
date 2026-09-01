from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from kospi200_phase4e import runner as phase4e_runner
from kospi200_phase4e.modeling import FrozenModelBundle, PRIMARY_C, SCHEMA_VERSION


REQUIRED_ARTIFACTS = {
    "audit.json",
    "component_hashes.json",
    "decision.json",
    "feature_contract.json",
    "fold_boundaries.json",
    "frozen_model_bundle.pkl",
    "label_audit.json",
    "manifest.json",
    "oof_scores.csv.gz",
    "selected_primary.json",
    "selection_metrics.csv",
}


class _DeterministicEstimator:
    def predict(self, values: object) -> list[float]:
        return [0.0] * len(values)  # type: ignore[arg-type]


def _metrics(*, c_years: int = 2, d_years: int = 2) -> tuple[dict[str, object], ...]:
    return (
        {
            "agent": "B_ONLY",
            "mean_rank_ic": 0.01,
            "nonnegative_years": 1,
            "mean_top10_target_quality": 0.01,
            "evaluated_years": 2,
        },
        {
            "agent": "C_ONLY",
            "mean_rank_ic": 0.03,
            "nonnegative_years": 2,
            "mean_top10_target_quality": 0.02,
            "evaluated_years": c_years,
        },
        {
            "agent": "D_SOFT_FUSION",
            "mean_rank_ic": 0.02,
            "nonnegative_years": 2,
            "mean_top10_target_quality": 0.02,
            "evaluated_years": d_years,
        },
    )


def _bundle(
    *,
    selection_rows: int = 4,
    c_years: int = 2,
    d_years: int = 2,
) -> FrozenModelBundle:
    estimator = _DeterministicEstimator()
    scores = tuple(
        {
            "date": "2019-01-02" if index < 2 else "2020-01-02",
            "ticker": f"{index + 1:06d}",
            "label_valid": index != 1,
        }
        for index in range(selection_rows)
    )
    return FrozenModelBundle(
        schema_version=SCHEMA_VERSION,
        freeze_date="2020-12-30",
        primary_agent=PRIMARY_C,
        agent_b_estimator=estimator,  # type: ignore[arg-type]
        agent_c_estimator=estimator,  # type: ignore[arg-type]
        agent_d_estimator=estimator,  # type: ignore[arg-type]
        agent_b_features=("b__phase4e_percentile",),
        agent_c_features=("c",),
        agent_d_features=(
            "agent_b_percentile",
            "agent_c_percentile",
            "fundamental_available",
        ),
        selection_metrics=_metrics(c_years=c_years, d_years=d_years),
        audit={
            "oof_roles": {
                "d_meta_training": [2017, 2018],
                "model_selection": [2019, 2020],
            },
            "oof_folds": [],
            "d_selection_audit": [
                {"year": 2019, "meta_training_oof_years": [2017, 2018]},
                {"year": 2020, "meta_training_oof_years": [2017, 2018, 2019]},
            ],
            "agent_d": {
                "fitted_state": {"coefficient": [0.4, 0.5, 0.1]},
            },
        },
        selection_oof_scores=scores,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Phase4ERunnerTests(unittest.TestCase):
    def test_model_gate_requires_both_years_for_selected_and_all_candidates(self) -> None:
        expected_keys = {
            ("2019-01-02", "000001"),
            ("2019-01-02", "000002"),
            ("2020-01-02", "000003"),
            ("2020-01-02", "000004"),
        }
        passing = phase4e_runner._model_gate(_bundle(), expected_keys)
        self.assertTrue(passing["both_selection_years_evaluated"])
        self.assertTrue(passing["all_candidates_both_years_evaluated"])
        self.assertTrue(passing["all_pass"])

        selected_incomplete = phase4e_runner._model_gate(
            _bundle(c_years=1), expected_keys
        )
        self.assertFalse(selected_incomplete["both_selection_years_evaluated"])
        self.assertFalse(selected_incomplete["all_pass"])

        control_incomplete = phase4e_runner._model_gate(
            _bundle(d_years=1), expected_keys
        )
        self.assertTrue(control_incomplete["both_selection_years_evaluated"])
        self.assertFalse(control_incomplete["all_candidates_both_years_evaluated"])
        self.assertFalse(control_incomplete["all_pass"])

    def test_run_preserves_full_u_t_and_writes_pinned_artifact_tree(self) -> None:
        sessions = ("2018-01-02", "2019-01-02", "2020-01-02")
        score_panel = pd.DataFrame(
            {
                "date": [
                    "2018-01-02",
                    "2019-01-02",
                    "2019-01-02",
                    "2020-01-02",
                    "2020-01-02",
                ],
                "ticker": ["000001", "000001", "000002", "000001", "000002"],
            }
        )
        labelled = score_panel.copy()
        labelled["exit_date"] = [
            "2018-02-01",
            "2019-02-01",
            "2019-02-01",
            "2020-02-03",
            "2020-02-03",
        ]
        labelled["label_valid"] = [True, True, False, True, True]
        labelled["target_quality_20"] = [0.01, 0.02, None, 0.03, 0.04]
        config = SimpleNamespace(
            label_and_model_start=date(2018, 1, 2),
            training_end=date(2020, 12, 30),
            sample_every_sessions=1,
            target_horizon_sessions=20,
            downside_penalty=0.5,
            base_commission_rate=0.0002,
            base_slippage_rate=0.001,
            cost_schedule=Path("unused-cost-schedule.csv"),
            excluded_tickers=frozenset({"005930", "000660"}),
        )
        inputs = SimpleNamespace(
            sessions=sessions,
            market=pd.DataFrame(),
            index=pd.DataFrame(),
            membership=pd.DataFrame(),
            audit={"input_tree_sha256": "a" * 64},
        )
        values = {
            "experiment_id": "EXP-20260901-001",
            "code_hash": "c" * 64,
            "config_hash": "f" * 64,
            "data_version": "d" * 64,
            "runtime_versions": phase4e_runner.runtime_versions(),
            "final_oos_accessed": False,
        }
        expected_bundle = replace(
            _bundle(selection_rows=4),
            selection_oof_scores=(
                {"date": "2019-01-02", "ticker": "000001", "label_valid": True},
                {"date": "2019-01-02", "ticker": "000002", "label_valid": False},
                {"date": "2020-01-02", "ticker": "000001", "label_valid": True},
                {"date": "2020-01-02", "ticker": "000002", "label_valid": True},
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4e"
            with (
                patch.object(phase4e_runner, "load_config", return_value=config),
                patch.object(
                    phase4e_runner,
                    "preflight_values",
                    return_value=(values, inputs),
                ),
                patch.object(phase4e_runner, "verify_preregistration"),
                patch.object(phase4e_runner, "build_score_panel", return_value=score_panel),
                patch.object(
                    phase4e_runner,
                    "attach_reset_safe_labels",
                    return_value=(labelled, {"label_rows": len(labelled)}),
                ),
                patch.object(
                    phase4e_runner,
                    "fit_frozen_model_bundle",
                    return_value=expected_bundle,
                ) as fit_bundle,
            ):
                manifest = phase4e_runner.run(Path("unused-config.json"), output)

            fit_input = fit_bundle.call_args.args[0]
            self.assertEqual(len(fit_input), len(labelled))
            self.assertEqual(int((~fit_input["label_valid"]).sum()), 1)
            self.assertEqual(len(pd.read_csv(output / "oof_scores.csv.gz")), 4)

            files = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertTrue(REQUIRED_ARTIFACTS.issubset(files))
            self.assertTrue(
                (REQUIRED_ARTIFACTS - {"manifest.json"}).issubset(
                    set(manifest["output_sha256"])
                )
            )
            for relative, expected_hash in manifest["output_sha256"].items():
                self.assertEqual(_sha256(output / relative), expected_hash)
            self.assertEqual(
                manifest["artifact_tree_sha256"],
                phase4e_runner.artifact_tree_sha256(output),
            )
            self.assertTrue(manifest["phase4e_model_gate_pass"])
            self.assertTrue(manifest["phase5r_eligible"])

            selected = json.loads(
                (output / "selected_primary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(selected["primary_agent"], PRIMARY_C)
            self.assertTrue(selected["phase4e_model_gate_pass"])


if __name__ == "__main__":
    unittest.main()
