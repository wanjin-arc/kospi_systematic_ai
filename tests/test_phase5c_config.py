from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kospi100_rank_persistence.cli import build_parser
from kospi100_rank_persistence.config import EXPERIMENT_ID, INHERITED_CANDIDATE, load_config
from kospi100_rank_persistence.runner import confirm_development_test


class Phase5CConfigTests(unittest.TestCase):
    def _mutated(self, mutate) -> Path:
        payload = json.loads(Path("configs/phase5c_persistent_ranking.json").read_text(encoding="utf-8"))
        mutate(payload)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        json.dump(payload, handle)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_contract_and_cli_are_frozen(self) -> None:
        config = load_config(Path("configs/phase5c_persistent_ranking.json"))
        self.assertEqual(config.experiment_id, EXPERIMENT_ID)
        self.assertEqual(config.inherited_candidate, INHERITED_CANDIDATE)
        self.assertEqual((config.ema_span_sessions, config.desired_entry_rank), (5, 10))
        self.assertEqual((config.fallback_max_rank, config.exit_rank), (20, 20))
        self.assertEqual(config.maximum_holding_sessions, 20)
        parsed = build_parser().parse_args(
            ["run", "--config", "configs/phase5c_persistent_ranking.json", "--output", "example"]
        )
        self.assertEqual(parsed.command, "run")

    def test_boundary_and_policy_mutations_are_rejected(self) -> None:
        boundary = self._mutated(lambda payload: payload.__setitem__("maximum_permitted_date", "2021-12-31"))
        with self.assertRaises(PermissionError):
            load_config(boundary)
        policy = self._mutated(
            lambda payload: payload["ranking_policy"].__setitem__("ema_span_sessions", 10)
        )
        with self.assertRaises(ValueError):
            load_config(policy)

    def test_development_test_and_disallowed_path_fail_closed(self) -> None:
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

    def test_registry_is_preregistered_before_execution(self) -> None:
        with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            rows = {row["experiment_id"]: row for row in csv.DictReader(handle)}
        self.assertIn(EXPERIMENT_ID, rows)
        self.assertIn(rows[EXPERIMENT_ID]["status"], {"preregistered", "adaptive_diagnostic_completed"})
        self.assertEqual(rows[EXPERIMENT_ID]["development_test_metrics_json"], "NOT_ACCESSED")


if __name__ == "__main__":
    unittest.main()
