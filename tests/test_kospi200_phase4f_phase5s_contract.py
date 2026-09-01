from __future__ import annotations

import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from kospi200_phase4e.config import EXPERIMENT_ID as HISTORICAL_PHASE4E_EXPERIMENT_ID
from kospi200_phase5r.config import EXPERIMENT_ID as HISTORICAL_PHASE5R_EXPERIMENT_ID
from kospi200_phase4f import config as phase4f_config
from kospi200_phase4f import modeling as phase4f_modeling
from kospi200_phase4f import runner as phase4f_runner
from kospi200_phase5s import config as phase5s_config
from kospi200_phase5s import runner as phase5s_runner


ROOT = Path(__file__).resolve().parents[1]
PHASE4F_CONFIG = ROOT / "configs" / "v2_phase4f_share_change_safe_model.json"
PHASE5S_CONFIG = ROOT / "configs" / "v2_phase5s_share_change_safe_integrity.json"

EXPECTED_BOUNDARY = {
    "share_change_gross_ratio_threshold": 1.20,
    "source": "CONSECUTIVE_SESSION_LISTED_SHARES",
    "semantics": "CANDIDATE_ONLY_NOT_EXECUTABLE_ACTION",
    "candidate_uses_price": False,
    "label_policy": "INVALIDATE_SIGNAL_TO_EXIT_CROSSING",
    "technical_policy": "RESET_SEGMENT_AT_CANDIDATE_OR_OBSERVATION_GAP",
}


def _forbidden_training_calls(module: object) -> list[str]:
    tree = ast.parse(inspect.getsource(module))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "fit",
            "fit_transform",
            "partial_fit",
        }:
            found.append(node.func.attr)
        if isinstance(node.func, ast.Name) and node.func.id.startswith("fit_"):
            found.append(node.func.id)
    return found


class Phase4FPhase5SVersionContractTests(unittest.TestCase):
    def test_new_experiment_and_schema_ids_are_distinct_from_superseded_history(self) -> None:
        self.assertEqual(phase4f_config.EXPERIMENT_ID, "EXP-20260901-003")
        self.assertEqual(
            phase4f_config.SCHEMA_VERSION,
            "v2-phase4f-share-change-safe-model-v1",
        )
        self.assertEqual(
            phase4f_modeling.SCHEMA_VERSION,
            "v2-phase4f-share-change-safe-frozen-model-bundle-v1",
        )
        self.assertEqual(phase5s_config.EXPERIMENT_ID, "EXP-20260901-004")
        self.assertEqual(
            phase5s_config.PHASE4F_EXPERIMENT_ID,
            "EXP-20260901-003",
        )
        self.assertEqual(
            phase5s_config.SCHEMA_VERSION,
            "v2-phase5s-share-change-safe-integrity-v1",
        )
        self.assertNotEqual(phase4f_config.EXPERIMENT_ID, "EXP-20260901-001")
        self.assertNotEqual(phase5s_config.EXPERIMENT_ID, "EXP-20260901-002")

    def test_release_manifest_schema_ids_are_versioned(self) -> None:
        phase4_source = inspect.getsource(phase4f_runner.run)
        phase5_source = inspect.getsource(phase5s_runner.run)
        self.assertIn(
            "v2-phase4f-share-change-safe-model-release-v1", phase4_source
        )
        self.assertIn(
            "v2-phase5s-share-change-safe-integrity-release-v1", phase5_source
        )

    def test_superseded_experiment_ids_remain_historical_and_distinct(self) -> None:
        self.assertEqual(HISTORICAL_PHASE4E_EXPERIMENT_ID, "EXP-20260901-001")
        self.assertEqual(HISTORICAL_PHASE5R_EXPERIMENT_ID, "EXP-20260901-002")
        self.assertNotEqual(
            HISTORICAL_PHASE4E_EXPERIMENT_ID, phase4f_config.EXPERIMENT_ID
        )
        self.assertNotEqual(
            HISTORICAL_PHASE5R_EXPERIMENT_ID, phase5s_config.EXPERIMENT_ID
        )


class Phase4FPhase5SConfigContractTests(unittest.TestCase):
    def test_configs_load_with_same_share_change_boundary(self) -> None:
        phase4 = phase4f_config.load_config(PHASE4F_CONFIG)
        phase5 = phase5s_config.load_config(PHASE5S_CONFIG)
        self.assertEqual(phase4.experiment_id, "EXP-20260901-003")
        self.assertEqual(phase5.experiment_id, "EXP-20260901-004")
        self.assertEqual(phase5.phase4f_experiment_id, "EXP-20260901-003")
        self.assertEqual(phase4.share_change_gross_ratio_threshold, 1.20)
        self.assertEqual(phase5.share_change_gross_ratio_threshold, 1.20)
        for config in (phase4, phase5):
            boundary = config.payload.get("share_change_boundary")
            self.assertIsInstance(boundary, dict)
            for key, expected in EXPECTED_BOUNDARY.items():
                self.assertEqual(boundary.get(key), expected, key)

    def test_boundary_threshold_or_price_dependency_mutation_is_rejected(self) -> None:
        for config_path, loader in (
            (PHASE4F_CONFIG, phase4f_config.load_config),
            (PHASE5S_CONFIG, phase5s_config.load_config),
        ):
            original = json.loads(config_path.read_text(encoding="utf-8"))
            for key, changed in (
                ("share_change_gross_ratio_threshold", 1.19),
                ("candidate_uses_price", True),
                ("source", "PRICE_AND_SHARES"),
                ("semantics", "EXECUTABLE_ACTION"),
                ("label_policy", "IGNORE"),
                ("technical_policy", "NO_RESET"),
            ):
                with self.subTest(config=config_path.name, key=key), tempfile.TemporaryDirectory() as directory:
                    payload = json.loads(json.dumps(original))
                    payload["share_change_boundary"][key] = changed
                    path = Path(directory) / "config.json"
                    path.write_text(
                        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                    )
                    with self.assertRaises((ValueError, PermissionError)):
                        loader(path)


class Phase5SPredictOnlyRunnerTests(unittest.TestCase):
    def test_runner_module_contains_no_estimator_training_call(self) -> None:
        self.assertEqual(_forbidden_training_calls(phase5s_runner), [])

    def test_run_does_not_import_or_call_backtest_engine(self) -> None:
        module_tree = ast.parse(inspect.getsource(phase5s_runner))
        engine_imports = [
            node
            for node in ast.walk(module_tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "kospi100_backtest.engine"
        ]
        self.assertEqual(engine_imports, [])

        run_tree = ast.parse(inspect.getsource(phase5s_runner.run))
        identifiers = {
            node.id for node in ast.walk(run_tree) if isinstance(node, ast.Name)
        }
        attributes = {
            node.attr for node in ast.walk(run_tree) if isinstance(node, ast.Attribute)
        }
        self.assertNotIn("BacktestEngine", identifiers)
        self.assertNotIn("backtest_engine", identifiers)
        self.assertNotIn("BacktestEngine", attributes)
        self.assertNotIn("backtest_engine", attributes)

    def test_run_requests_predict_only_primary_without_controls(self) -> None:
        tree = ast.parse(inspect.getsource(phase5s_runner.run))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id == "predict_frozen_bundle"
            )
        ]
        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
        self.assertIn("include_controls", keywords)
        self.assertIsInstance(keywords["include_controls"], ast.Constant)
        self.assertIs(keywords["include_controls"].value, False)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
