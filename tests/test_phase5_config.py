from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kospi100_ranking.config import EXPECTED_CANDIDATES, load_config
from kospi100_ranking.runner import confirm_development_test, dependency_hash


class Phase5ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path("configs/phase5_ranking.json")

    def _mutated(self, mutate) -> Path:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        mutate(payload)
        temporary = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        json.dump(payload, temporary)
        temporary.close()
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_frozen_feature_period_candidates_and_boundaries(self) -> None:
        config = load_config(self.path)
        self.assertEqual(config.payload["feature_set"]["features"], ["reversal_5"])
        self.assertEqual(config.candidate_order, EXPECTED_CANDIDATES)
        self.assertEqual((config.purge_sessions, config.embargo_sessions), (20, 20))
        self.assertEqual(config.maximum_permitted_date.isoformat(), "2021-12-31")
        self.assertFalse(config.payload["development_test_access"])

    def test_additional_feature_is_rejected(self) -> None:
        path = self._mutated(lambda payload: payload["feature_set"]["features"].append("momentum_20"))
        with self.assertRaises(ValueError):
            load_config(path)

    def test_development_test_option_is_rejected(self) -> None:
        path = self._mutated(lambda payload: payload.__setitem__("development_test_access", True))
        with self.assertRaises(PermissionError):
            load_config(path)

    def test_sealed_path_is_rejected(self) -> None:
        path = self._mutated(lambda payload: payload.__setitem__("data_root", "data/sealed/example"))
        with self.assertRaises(PermissionError):
            load_config(path)

    def test_confirm_command_remains_locked(self) -> None:
        with self.assertRaises(PermissionError):
            confirm_development_test()

    def test_dependency_lock_contains_exact_sklearn(self) -> None:
        _, versions = dependency_hash()
        self.assertEqual(versions["scikit_learn"], "1.9.0")


if __name__ == "__main__":
    unittest.main()
