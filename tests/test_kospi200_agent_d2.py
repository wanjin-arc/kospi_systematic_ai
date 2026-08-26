from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_c.runner import sha256
from kospi200_agent_d2.runner import METHODS, _read_upstream, combine_method_scores, create_orders


class AgentD2Tests(unittest.TestCase):
    def setUp(self):
        self.agent_c = pd.DataFrame({
            "date": ["2020-01-02"] * 3,
            "ticker": ["000001", "000002", "000003"],
            "agent_c2_score": [0.20, 0.10, 0.08],
        })
        self.agent_b = pd.DataFrame({
            "date": ["2020-01-02"] * 2,
            "ticker": ["000001", "000002"],
            "agent_b2_percentile": [0.10, 1.00],
            "broad_quality_eligible": [False, True],
        })

    def test_serial_method_restricts_to_b2_top80(self):
        result = combine_method_scores(self.agent_b, self.agent_c, "B2_TOP80_SERIAL")
        self.assertEqual(result["ticker"].tolist(), ["000002"])

    def test_risk_calibration_never_removes_c2_stock(self):
        result = combine_method_scores(self.agent_b, self.agent_c, "B2_RISK_CALIBRATION")
        self.assertEqual(set(result["ticker"]), set(self.agent_c["ticker"]))
        self.assertEqual(result.iloc[0]["ticker"], "000002")

    def test_control_does_not_use_b2_to_change_order(self):
        result = combine_method_scores(self.agent_b, self.agent_c, "C2_ONLY_CONTROL")
        self.assertEqual(result.sort_values("decision_rank")["ticker"].tolist(), ["000001", "000002", "000003"])

    def test_orders_use_next_open_and_rank_weight(self):
        scored = combine_method_scores(self.agent_b, self.agent_c, "C2_ONLY_CONTROL")
        market = pd.DataFrame({
            "date": ["2020-01-02"] * 3 + ["2020-01-03"] * 3,
            "ticker": ["000001", "000002", "000003"] * 2,
            "open": [100, 100, 100, 101, 101, 101],
            "close": [100, 100, 100, 101, 101, 101],
            "volume": [100] * 6,
        })
        config = {
            "entry_c2_score_floor": 0.05, "daily_entry_rank_limit": 5,
            "high_weight_rank_limit": 2, "target_weight_high": 0.11,
            "target_weight_low": 0.05, "gap_veto_rate": 0.05,
            "stop_loss_rate": 0.05, "take_profit_rate": 0.10,
            "maximum_holding_sessions": 10,
        }
        orders, vetoes = create_orders(scored, market, ["2020-01-02", "2020-01-03"], config, "C2_ONLY_CONTROL")
        self.assertEqual(vetoes, 0)
        self.assertEqual(len(orders), 3)
        self.assertEqual(str(orders[0].target_weight), "0.11")
        self.assertEqual(str(orders[2].target_weight), "0.05")
        self.assertEqual(orders[0].signal_date.isoformat(), "2020-01-02")
        self.assertEqual(orders[0].execute_date.isoformat(), "2020-01-03")

    def test_config_freezes_both_requested_methods_and_official_index(self):
        config = json.loads(Path("configs/v2_phase4b_agent_d2.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(config["methods"]), METHODS)
        self.assertEqual(config["benchmark"], "OFFICIAL_KRX_KOSPI200_CLOSE_1028")
        self.assertEqual(config["same_bar_policy"], "STOP_FIRST")
        self.assertEqual(config["take_profit_rate"], 2 * config["stop_loss_rate"])
        self.assertFalse(config["final_oos_access"])

    def test_upstream_hash_is_checked_before_score_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            score = root / "scores.csv"
            manifest = root / "manifest.json"
            score.write_text("date,ticker,score\n2020-01-02,000001,1\n", encoding="utf-8")
            manifest.write_text(json.dumps({"output_sha256": {"scores.csv": sha256(score)}}), encoding="utf-8")
            _read_upstream(score, manifest, "scores.csv")
            score.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash 불일치"):
                _read_upstream(score, manifest, "scores.csv")


if __name__ == "__main__":
    unittest.main()
