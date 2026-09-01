import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_b2.runner import attach_quality_target, load_official_index


class AgentB2Tests(unittest.TestCase):
    def test_config_freezes_official_index_and_quality_target(self):
        config = json.loads(Path("configs/v2_phase2b_agent_b_quality.json").read_text(encoding="utf-8"))
        self.assertEqual(config["target_horizon_sessions"], 63)
        self.assertEqual(config["downside_penalty"], 0.5)
        self.assertEqual(config["broad_quality_size"], 80)
        self.assertEqual(config["purge_sessions"], 63)
        self.assertEqual(config["embargo_sessions"], 63)

    def test_target_uses_t_plus_1_and_t_plus_64_and_official_excess(self):
        sessions = [f"2020-01-{day:02d}" for day in range(1, 66)]
        market = pd.DataFrame({"date": sessions, "ticker": "000001", "open": [100.0] * 64 + [120.0], "close": [100.0] * 65})
        index = pd.DataFrame({"date": sessions, "open": [100.0] * 64 + [110.0]})
        frame = pd.DataFrame({"date": [sessions[0]], "ticker": ["000001"]})
        result = attach_quality_target(frame, market, index, sessions, 63, 0.5)
        self.assertAlmostEqual(result.loc[0, "target_excess_63"], 0.1)
        self.assertAlmostEqual(result.loc[0, "target_mae_63"], 0.0)
        self.assertAlmostEqual(result.loc[0, "target_quality_63"], 0.1)

    def test_official_index_rejects_non_1028(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.csv"
            pd.DataFrame({"date": ["2020-01-02"], "open": [1], "high": [1], "low": [1], "close": [1], "index_code": [1001]}).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "1028"):
                load_official_index(path)
