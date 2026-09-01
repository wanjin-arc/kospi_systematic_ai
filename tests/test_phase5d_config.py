from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kospi100_selective_ranking.cli import build_parser
from kospi100_selective_ranking.config import EXPERIMENT_ID, load_config
from kospi100_selective_ranking.runner import confirm_development_test


class Phase5DConfigTests(unittest.TestCase):
    def _mutated(self, mutate) -> Path:
        payload = json.loads(Path("configs/phase5d_selective_ranking.json").read_text(encoding="utf-8"))
        mutate(payload)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        json.dump(payload, handle)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_reused_validation_and_variable_holdings_are_frozen(self) -> None:
        config = load_config(Path("configs/phase5d_selective_ranking.json"))
        self.assertEqual(config.experiment_id, EXPERIMENT_ID)
        self.assertEqual(config.base.maximum_permitted_date.isoformat(), "2021-12-31")
        self.assertEqual(config.payload["market_policy"]["maximum_holdings_by_regime"], {
            "risk_on": 10,
            "neutral": 5,
            "risk_off": 0,
        })
        self.assertEqual(config.payload["portfolio"]["required_minimum_holdings"], 0)
        self.assertFalse(config.payload["diagnostic_reporting"]["average_cash_is_hard_gate"])
        parsed = build_parser().parse_args(
            ["run", "--config", "configs/phase5d_selective_ranking.json", "--output", "example"]
        )
        self.assertEqual(parsed.command, "run")

    def test_boundary_cash_and_capacity_mutations_are_rejected(self) -> None:
        boundary = self._mutated(lambda payload: payload.__setitem__("maximum_permitted_date", "2023-12-31"))
        with self.assertRaises(PermissionError):
            load_config(boundary)
        cash = self._mutated(
            lambda payload: payload["diagnostic_reporting"].__setitem__("average_cash_is_hard_gate", True)
        )
        with self.assertRaises(ValueError):
            load_config(cash)
        capacity = self._mutated(
            lambda payload: payload["market_policy"]["maximum_holdings_by_regime"].__setitem__("risk_off", 1)
        )
        with self.assertRaises(ValueError):
            load_config(capacity)

    def test_development_test_and_unapproved_paths_fail_closed(self) -> None:
        development = self._mutated(lambda payload: payload.__setitem__("development_test_access", True))
        with self.assertRaises(PermissionError):
            load_config(development)
        disallowed = self._mutated(
            lambda payload: payload.__setitem__("data_root", "data/development/example")
        )
        with self.assertRaises(PermissionError):
            load_config(disallowed)
        with self.assertRaises(PermissionError):
            confirm_development_test()

    def test_registry_marks_reused_validation_not_test(self) -> None:
        with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            rows = {row["experiment_id"]: row for row in csv.DictReader(handle)}
        self.assertIn(EXPERIMENT_ID, rows)
        self.assertIn(rows[EXPERIMENT_ID]["status"], {"preregistered", "reused_validation_diagnostic_completed"})
        self.assertEqual(rows[EXPERIMENT_ID]["development_test_metrics_json"], "NOT_ACCESSED")


if __name__ == "__main__":
    unittest.main()
