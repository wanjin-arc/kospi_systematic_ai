from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

from kospi100_baseline.features import _corporate_action_blackout, _feature_segments

sys.path.insert(0, str(Path("tools").resolve()))
from build_phase1c_2004_2018_partition import _infer_resets, _membership_spells  # noqa: E402


class Phase1CPartitionTests(unittest.TestCase):
    def test_actual_partition_has_2004_boundary_and_no_protected_rows(self) -> None:
        root = Path("data/processed/v25_phase5i_train_internal_2004_2018")
        payload = json.loads((root / "partition.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["min_date"], "2004-01-02")
        self.assertEqual(payload["max_date"], "2018-12-31")
        self.assertEqual(payload["audit"]["actual_loaded_min_date"], "2004-01-02")
        self.assertEqual(payload["audit"]["membership_count_distribution"], {"99": 2, "100": 1490})
        self.assertFalse(payload["audit"]["corporate_action_terms_inferred"])
        self.assertFalse(payload["audit"]["development_test_input_loaded"])
        self.assertFalse(payload["audit"]["final_oos_accessed"])

    def test_membership_spells_reset_on_session_gap(self) -> None:
        sessions = pd.DatetimeIndex(pd.to_datetime(["2004-01-02", "2004-01-05", "2004-01-06"]))
        membership = pd.DataFrame(
            {"date": pd.to_datetime(["2004-01-02", "2004-01-06"]), "ticker": ["000001", "000001"], "name": ["A", "A"]}
        )
        result = _membership_spells(membership, sessions)
        self.assertEqual(result["membership_spell_id"].nunique(), 2)

    def test_fail_closed_reset_only_on_transition_or_large_consecutive_gap(self) -> None:
        sessions = pd.DatetimeIndex(pd.to_datetime(["2004-01-02", "2004-01-05", "2004-01-06", "2004-01-07"]))
        history = pd.DataFrame(
            {
                "date": sessions,
                "security_id": ["S"] * 4,
                "ticker": ["000001"] * 4,
                "name": ["A"] * 4,
                "open": [100, 0, 0, 50],
                "high": [101, 0, 0, 52],
                "low": [99, 0, 0, 49],
                "close": [100, 100, 100, 50],
                "volume": [100, 0, 0, 100],
                "listed_shares": [1000] * 4,
            }
        )
        resets = _infer_resets(history, sessions)
        self.assertEqual(resets["feature_boundary_date"].dt.strftime("%Y-%m-%d").tolist(), ["2004-01-05", "2004-01-07"])
        self.assertTrue(resets["feature_handling"].str.startswith("RESET_").all())

    def test_boundary_only_reset_segments_without_fake_filing_blackout(self) -> None:
        panel = pd.DataFrame(
            {"date": pd.to_datetime(["2004-01-02", "2004-01-05"]), "security_id": ["S", "S"]}
        )
        actions = pd.DataFrame(
            {
                "canonical_event_id": ["R"],
                "security_id": ["S"],
                "feature_handling": ["RESET_PRICE_CONTINUITY_AT_UNVERIFIED_ACTION"],
                "feature_boundary_date": pd.to_datetime(["2004-01-05"]),
                "first_filing_date": [pd.NaT],
                "phase1_data_status": ["FEATURE_RESET_ONLY"],
                "primary_source": ["KRX_RAW"],
                "portfolio_terms_status": ["NOT_USED_BEFORE_2011_VALIDATION"],
            }
        )
        self.assertEqual(_feature_segments(panel, actions).tolist(), [0, 1])
        blocked, late = _corporate_action_blackout(panel, actions)
        self.assertFalse(blocked.any())
        self.assertEqual(late, 0)


if __name__ == "__main__":
    unittest.main()
