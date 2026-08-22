from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kospi100_absolute_alpha.cli import build_parser
from kospi100_absolute_alpha.config import EXPERIMENT_ID, load_config
from kospi100_absolute_alpha.runner import confirm_development_test


class Phase5EConfigTests(unittest.TestCase):
    def _mutated(self, mutate) -> Path:
        payload = json.loads(Path("configs/phase5e_absolute_alpha.json").read_text(encoding="utf-8"))
        mutate(payload)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        json.dump(payload, handle)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_absolute_target_dual_model_and_no_trade_contract_are_frozen(self) -> None:
        config = load_config(Path("configs/phase5e_absolute_alpha.json"))
        self.assertEqual(config.experiment_id, EXPERIMENT_ID)
        self.assertEqual(config.base.maximum_permitted_date.isoformat(), "2021-12-31")
        self.assertEqual(config.ridge_alpha, 100.0)
        self.assertEqual(config.logistic_c, 1.0)
        self.assertEqual(config.entry_net_excess, 0.005)
        self.assertEqual(config.entry_probability, 0.60)
        self.assertEqual(config.base.maximum_holdings, 10)
        self.assertEqual(config.payload["portfolio"]["required_minimum_holdings"], 0)
        self.assertEqual(config.payload["target"]["cross_sectional_transform"], "none")
        parsed = build_parser().parse_args([
            "run", "--config", "configs/phase5e_absolute_alpha.json", "--output", "example"
        ])
        self.assertEqual(parsed.command, "run")

    def test_target_threshold_model_and_boundary_mutations_are_rejected(self) -> None:
        for path in (
            self._mutated(lambda p: p["target"].__setitem__("cross_sectional_transform", "rank")),
            self._mutated(lambda p: p["no_trade_policy"].__setitem__("entry_minimum_positive_probability", 0.55)),
            self._mutated(lambda p: p["models"].__setitem__("ridge_alpha", 10.0)),
        ):
            with self.assertRaises(ValueError):
                load_config(path)
        boundary = self._mutated(lambda p: p.__setitem__("maximum_permitted_date", "2023-12-31"))
        with self.assertRaises(PermissionError):
            load_config(boundary)

    def test_development_test_and_unapproved_paths_fail_closed(self) -> None:
        development = self._mutated(lambda p: p.__setitem__("development_test_access", True))
        with self.assertRaises(PermissionError):
            load_config(development)
        disallowed = self._mutated(lambda p: p.__setitem__("data_root", "data/development/example"))
        with self.assertRaises(PermissionError):
            load_config(disallowed)
        sealed = self._mutated(lambda p: p.__setitem__("data_root", "data/sealed/example"))
        with self.assertRaises(PermissionError):
            load_config(sealed)
        with self.assertRaises(PermissionError):
            confirm_development_test()

    def test_registry_is_preregistered_without_development_test_result(self) -> None:
        with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            rows = {row["experiment_id"]: row for row in csv.DictReader(handle)}
        self.assertIn(EXPERIMENT_ID, rows)
        self.assertIn(rows[EXPERIMENT_ID]["status"], {"preregistered", "adaptive_diagnostic_completed"})
        self.assertEqual(rows[EXPERIMENT_ID]["development_test_metrics_json"], "NOT_ACCESSED")
        self.assertEqual(rows[EXPERIMENT_ID]["final_oos_accessed"], "false")


if __name__ == "__main__":
    unittest.main()
