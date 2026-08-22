from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kospi100_multifactor.config import CANDIDATES, STOCK_FEATURES, load_analysis_config, load_selection_config
from kospi100_multifactor.cli import build_parser
from kospi100_multifactor.runner import confirm_development_test, dependency_hash


class Phase4BConfigTests(unittest.TestCase):
    def _mutated(self, source: str, mutate) -> Path:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        mutate(payload)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        json.dump(payload, handle)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_analysis_contract_is_frozen(self) -> None:
        config = load_analysis_config(Path("configs/phase4b_multifactor.json"))
        self.assertEqual(config.stock_features, STOCK_FEATURES)
        self.assertEqual(len(config.regime_features), 5)
        self.assertEqual(len(config.interactions), 6)
        self.assertEqual(config.maximum_permitted_date.isoformat(), "2018-12-31")
        self.assertEqual((config.purge_sessions, config.embargo_sessions), (20, 20))

    def test_feature_and_boundary_mutation_are_rejected(self) -> None:
        feature = self._mutated(
            "configs/phase4b_multifactor.json", lambda payload: payload["stock_features"].pop()
        )
        with self.assertRaises(ValueError):
            load_analysis_config(feature)
        boundary = self._mutated(
            "configs/phase4b_multifactor.json",
            lambda payload: payload.__setitem__("maximum_permitted_date", "2021-12-31"),
        )
        with self.assertRaises(PermissionError):
            load_analysis_config(boundary)

    def test_selection_candidates_daily_rank_and_holding_are_frozen(self) -> None:
        config = load_selection_config(Path("configs/phase5b_multifactor_ranking.json"))
        self.assertEqual(config.candidate_order, CANDIDATES)
        self.assertEqual((config.holding_sessions, config.maximum_holdings), (10, 10))
        self.assertEqual(config.payload["portfolio"]["entry_priority"], "daily_score_desc_security_id_asc")

    def test_development_test_and_disallowed_path_are_rejected(self) -> None:
        development = self._mutated(
            "configs/phase4b_multifactor.json",
            lambda payload: payload.__setitem__("development_test_access", True),
        )
        with self.assertRaises(PermissionError):
            load_analysis_config(development)
        disallowed = self._mutated(
            "configs/phase4b_multifactor.json",
            lambda payload: payload.__setitem__("data_root", "data/development/example"),
        )
        with self.assertRaises(PermissionError):
            load_analysis_config(disallowed)
        with self.assertRaises(PermissionError):
            confirm_development_test()

    def test_dependency_lock_contains_exact_sklearn(self) -> None:
        _, versions = dependency_hash()
        self.assertEqual(versions["scikit_learn"], "1.9.0")

    def test_package_cli_and_registry_experiments_exist(self) -> None:
        parsed = build_parser().parse_args(
            ["analyze", "--config", "configs/phase4b_multifactor.json", "--output", "example"]
        )
        self.assertEqual(parsed.command, "analyze")
        with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            rows = {row["experiment_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["EXP-20260823-001"]["status"], "analysis_completed")
        self.assertEqual(rows["EXP-20260823-002"]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
