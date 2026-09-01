from __future__ import annotations

import ast
import hashlib
import inspect
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from kospi200_phase4e.modeling import (
    FrozenModelBundle,
    PRIMARY_C,
    SCHEMA_VERSION,
    bundle_state_hashes,
)
from kospi200_phase4e.runner import runtime_versions as phase4e_runtime_versions
from kospi200_phase5r import runner as phase5r_runner


class _PredictOnlyEstimator:
    """Bundle verifier test double; loading it must never invoke training."""

    def fit(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("Phase 5R에서 fit이 호출됐습니다.")

    def predict(self, values: object) -> list[float]:
        return [0.0] * len(values)  # type: ignore[arg-type]


def _bundle(*, freeze_date: str = "2020-12-31") -> FrozenModelBundle:
    estimator = _PredictOnlyEstimator()
    return FrozenModelBundle(
        schema_version=SCHEMA_VERSION,
        freeze_date=freeze_date,
        primary_agent=PRIMARY_C,
        agent_b_estimator=estimator,  # type: ignore[arg-type]
        agent_c_estimator=estimator,  # type: ignore[arg-type]
        agent_d_estimator=estimator,  # type: ignore[arg-type]
        agent_b_features=("b__phase4e_percentile",),
        agent_c_features=("c",),
        agent_d_features=("agent_b_percentile", "agent_c_percentile", "fundamental_available"),
        selection_metrics=(),
        audit={"final_fit_boundary": {"signal_max": "2020-12-30", "exit_max": "2020-12-30"}},
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_release(
    root: Path,
    *,
    frozen_bundle: FrozenModelBundle | None = None,
) -> SimpleNamespace:
    bundle_path = root / "frozen_model_bundle.pkl"
    manifest_path = root / "manifest.json"
    bundle = frozen_bundle or _bundle()
    bundle_path.write_bytes(pickle.dumps(bundle, protocol=5))
    (root / "decision.json").write_text('{"decision":"eligible"}\n', encoding="utf-8")
    bundle_sha = _sha256(bundle_path)
    state = bundle_state_hashes(bundle)
    tree_sha = phase5r_runner._artifact_tree_sha256(manifest_path, bundle_path) if manifest_path.exists() else ""
    if not tree_sha:
        # The production helper resolves the excluded manifest strictly, so create a placeholder first.
        manifest_path.write_text("{}\n", encoding="utf-8")
        tree_sha = phase5r_runner._artifact_tree_sha256(manifest_path, bundle_path)
    manifest = {
        "experiment_id": "EXP-20260901-001",
        "primary_agent": PRIMARY_C,
        "bundle_sha256": bundle_sha,
        "model_hash": state["model_state_hash"],
        "model_state_hash": state["model_state_hash"],
        "artifact_tree_sha256": tree_sha,
        "phase4e_model_gate_pass": False,
        "phase5r_eligible": False,
        "phase5r_predict_only_diagnostic_allowed": True,
        "fit_max_date": "2020-12-30",
        "fit_max_exit_date": "2020-12-30",
        "agent_b_features": ["b__phase4e_percentile"],
        "agent_c_features": ["c"],
        "agent_d_features": [
            "agent_b_percentile",
            "agent_c_percentile",
            "fundamental_available",
        ],
        "component_sha256": state["component_sha256"],
        "input_hashes": {"runtime_versions": phase5r_runner._runtime_versions()},
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return SimpleNamespace(
        phase4_hashes_resolved=True,
        phase4e_bundle=bundle_path,
        phase4e_manifest=manifest_path,
        phase4e_bundle_sha256=bundle_sha,
        phase4e_manifest_sha256=_sha256(manifest_path),
        phase4e_artifact_tree_sha256=tree_sha,
        phase4e_model_hash=state["model_state_hash"],
        phase4e_experiment_id="EXP-20260901-001",
        payload={
            "agent_b": {"features": ["b"], "feature_suffix": "__phase4e_percentile"},
            "agent_c": {"features": ["c"]},
        },
    )


def _rewrite_manifest(config: SimpleNamespace, **changes: object) -> None:
    manifest = json.loads(config.phase4e_manifest.read_text(encoding="utf-8"))
    manifest.update(changes)
    config.phase4e_manifest.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    config.phase4e_manifest_sha256 = _sha256(config.phase4e_manifest)


class Phase4EPhase5RRunnerContractTests(unittest.TestCase):
    def test_training_and_prediction_runtime_contracts_are_identical(self) -> None:
        self.assertEqual(phase5r_runner._runtime_versions(), phase4e_runtime_versions())

    def test_code_hash_covers_predict_and_execution_modules(self) -> None:
        required = {
            "src/kospi200_phase4e/__init__.py",
            "src/kospi200_phase4e/modeling.py",
            "src/kospi200_phase5r/__init__.py",
            "src/kospi200_phase5r/cli.py",
            "src/kospi200_phase5r/modeling.py",
            "src/kospi100_backtest/config.py",
            "src/kospi100_backtest/costs.py",
            "src/kospi100_backtest/engine.py",
            "src/kospi100_backtest/io.py",
            "src/kospi100_backtest/types.py",
            "src/kospi200_agent_d/runner.py",
        }
        self.assertTrue(required.issubset(set(phase5r_runner.CODE_PATHS)))

    def test_phase5r_runner_contains_no_estimator_training_call(self) -> None:
        tree = ast.parse(inspect.getsource(phase5r_runner))
        forbidden: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "fit",
                "fit_transform",
                "partial_fit",
            }:
                forbidden.append(node.func.attr)
            if isinstance(node.func, ast.Name) and node.func.id.startswith("fit_"):
                forbidden.append(node.func.id)
        self.assertEqual(forbidden, [])

    def test_runner_requests_primary_only_prediction(self) -> None:
        tree = ast.parse(inspect.getsource(phase5r_runner.run))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "predict_frozen_bundle"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
        self.assertIn("include_controls", keywords)
        self.assertIsInstance(keywords["include_controls"], ast.Constant)
        self.assertIs(keywords["include_controls"].value, False)  # type: ignore[union-attr]

    def test_integrity_gate_inherits_phase4_model_gate_failure(self) -> None:
        gates, decision = phase5r_runner._integrity_decision(
            {"phase4e_model_gate_pass": False},
            {"stable_identity_contract_complete": True},
            (),
            {"canonical_ex2_return_evaluable": True},
        )
        self.assertFalse(gates["phase4e_model_gate"])
        self.assertEqual(
            decision,
            "REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT",
        )

    def test_run_contains_no_backtest_engine_call(self) -> None:
        tree = ast.parse(inspect.getsource(phase5r_runner.run))
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("_engine", called_names)
        self.assertNotIn("run", called_attributes)

    def test_frozen_bundle_loader_verifies_exact_bytes_and_never_fits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _write_release(root)

            loaded, manifest = phase5r_runner.load_frozen_bundle(config)
            self.assertEqual(loaded.primary_agent, PRIMARY_C)
            self.assertEqual(manifest["bundle_sha256"], config.phase4e_bundle_sha256)
            self.assertFalse(manifest["phase4e_model_gate_pass"])
            self.assertTrue(manifest["phase5r_predict_only_diagnostic_allowed"])

            config.phase4e_bundle.write_bytes(config.phase4e_bundle.read_bytes() + b"tampered")
            with self.assertRaises(PermissionError):
                phase5r_runner.load_frozen_bundle(config)

    def test_loader_does_not_repickle_loaded_estimators_for_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _write_release(Path(directory))
            with patch.object(
                phase5r_runner.pickle,
                "dumps",
                side_effect=AssertionError("loaded estimator를 다시 pickle하면 안 됩니다"),
            ):
                loaded, _ = phase5r_runner.load_frozen_bundle(config)
            self.assertEqual(loaded.primary_agent, PRIMARY_C)

    def test_loader_accepts_histgb_bundle_with_unstable_repickle_bytes(self) -> None:
        x_one = np.arange(16, dtype=float).reshape(-1, 1)
        x_three = np.column_stack((x_one[:, 0], x_one[:, 0] ** 2, x_one[:, 0] % 3))
        target = np.sin(x_one[:, 0])
        estimators = [
            HistGradientBoostingRegressor(max_iter=3, min_samples_leaf=2).fit(x_one, target),
            HistGradientBoostingRegressor(max_iter=3, min_samples_leaf=2).fit(x_one, target),
            HistGradientBoostingRegressor(max_iter=3, min_samples_leaf=2).fit(x_three, target),
        ]
        bundle = FrozenModelBundle(
            schema_version=SCHEMA_VERSION,
            freeze_date="2020-12-30",
            primary_agent=PRIMARY_C,
            agent_b_estimator=estimators[0],  # type: ignore[arg-type]
            agent_c_estimator=estimators[1],  # type: ignore[arg-type]
            agent_d_estimator=estimators[2],  # type: ignore[arg-type]
            agent_b_features=("b__phase4e_percentile",),
            agent_c_features=("c",),
            agent_d_features=(
                "agent_b_percentile",
                "agent_c_percentile",
                "fundamental_available",
            ),
            selection_metrics=(),
            audit={"final_fit_boundary": {"signal_max": "2020-12-30", "exit_max": "2020-12-30"}},
        )
        pre_serialization = bundle_state_hashes(bundle)
        with tempfile.TemporaryDirectory() as directory:
            config = _write_release(Path(directory), frozen_bundle=bundle)
            reloaded = pickle.loads(config.phase4e_bundle.read_bytes())
            self.assertNotEqual(pre_serialization, bundle_state_hashes(reloaded))
            accepted, _ = phase5r_runner.load_frozen_bundle(config)
            np.testing.assert_array_equal(
                accepted.agent_c_estimator.predict(x_one),
                estimators[1].predict(x_one),
            )

    def test_manifest_and_canonical_tree_are_both_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _write_release(Path(directory))
            config.phase4e_manifest.write_text(
                config.phase4e_manifest.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PermissionError, "manifest hash"):
                phase5r_runner.load_frozen_bundle(config)

            config = _write_release(Path(directory))
            (Path(directory) / "decision.json").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(PermissionError, "artifact tree"):
                phase5r_runner.load_frozen_bundle(config)

    def test_release_semantics_fail_closed(self) -> None:
        cases = (
            ({"phase4e_model_gate_pass": "false"}, "model gate"),
            ({"phase5r_predict_only_diagnostic_allowed": False}, "predict-only"),
            ({"fit_max_date": "2020-12-31"}, "fit_max_date"),
            ({"fit_max_exit_date": "2021-01-04"}, "fit_max_exit_date"),
            ({"agent_c_features": ["changed"]}, "agent_c_features"),
            ({"component_sha256": {"agent_b": "0", "agent_c": "0", "agent_d": "0"}}, "component"),
            ({"model_state_hash": "0" * 64}, "model-state"),
            ({"input_hashes": {"runtime_versions": {"python": "0"}}}, "runtime"),
        )
        for changes, message in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                config = _write_release(Path(directory))
                _rewrite_manifest(config, **changes)
                with self.assertRaisesRegex(PermissionError, message):
                    phase5r_runner.load_frozen_bundle(config)


if __name__ == "__main__":
    unittest.main()
