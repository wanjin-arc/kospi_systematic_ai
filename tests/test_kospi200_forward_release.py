import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from kospi200_forward_release import ContractError, build_shadow_orders, load_contract, validate_contract


CONFIG_PATH = Path("configs/v2_phase6_forward_shadow.json")


class ForwardReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_design_contract_is_valid_but_not_release_ready(self):
        validate_contract(self.config)
        with self.assertRaisesRegex(ContractError, "동결되기 전"):
            validate_contract(self.config, release_ready=True)

    def test_rejects_real_or_enabled_kis(self):
        for key, value in (("environment", "production"), ("enabled", True), ("network_calls", True), ("order_submission", True)):
            candidate = copy.deepcopy(self.config)
            candidate["kis"][key] = value
            with self.assertRaises(ContractError):
                validate_contract(candidate)

    def test_rejects_secrets_in_config(self):
        candidate = copy.deepcopy(self.config)
        candidate["kis"]["app_key"] = "must-not-be-here"
        with self.assertRaisesRegex(ContractError, "비밀값"):
            validate_contract(candidate)

    def test_rejects_old_or_protected_input(self):
        candidate = copy.deepcopy(self.config)
        candidate["evaluation_start"] = "2026-08-26"
        with self.assertRaisesRegex(ContractError, "2026-08-27"):
            validate_contract(candidate)
        candidate = copy.deepcopy(self.config)
        candidate["input_path"] = "forbidden/sealed/protected_oos/prices.csv"
        with self.assertRaisesRegex(ContractError, "Protected OOS"):
            validate_contract(candidate)

    def test_requires_b_xgbranker_c_lstm_cnn_and_serial_d(self):
        mutations = [
            ("agent_b", "family", "Ridge"),
            ("agent_b", "objective", "reg:squarederror"),
            ("agent_b", "top_n", 80),
            ("agent_c", "family", "HistGradientBoosting"),
            ("agent_d", "architecture", "parallel_weighted_sum"),
        ]
        for section, key, value in mutations:
            candidate = copy.deepcopy(self.config)
            candidate[section][key] = value
            with self.assertRaises(ContractError):
                validate_contract(candidate)

    def test_load_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "contract.json")
            path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_contract(path)["experiment_id"], "EXP-20260826-013")

    def test_shadow_orders_obey_b_top30_probability_gap_and_t_plus_1(self):
        ready = copy.deepcopy(self.config)
        ready["status"] = "release_frozen"
        ready["agent_b"]["model_hash"] = "b" * 64
        ready["agent_c"]["model_hash"] = "c" * 64
        ready["agent_d"]["selected_weights"] = {
            "agent_b": 0.25,
            "cnn_probability": 0.75,
            "inverse_volatility": 0.25,
        }
        signals = pd.DataFrame(
            [
                ["2026-08-27", "2026-08-28", "000001", 1, 0.70, 0.01],
                ["2026-08-27", "2026-08-28", "000002", 30, 0.60, -0.02],
                ["2026-08-27", "2026-08-28", "000003", 31, 0.90, 0.00],
                ["2026-08-27", "2026-08-28", "000004", 2, 0.90, 0.06],
                ["2026-08-27", "2026-08-28", "000005", 3, 0.54, 0.00],
            ],
            columns=["signal_date", "trade_date", "ticker", "agent_b_rank", "cnn_probability", "gap_from_previous_close"],
        )
        result = build_shadow_orders(signals, ready)
        self.assertEqual(result["ticker"].tolist(), ["000001", "000002"])
        self.assertEqual(result["target_weight"].tolist(), [0.11, 0.05])
        self.assertTrue((result["execution_mode"] == "SHADOW_ONLY").all())

    def test_rejects_same_day_execution(self):
        ready = copy.deepcopy(self.config)
        ready["agent_b"]["model_hash"] = "b" * 64
        ready["agent_c"]["model_hash"] = "c" * 64
        ready["agent_d"]["selected_weights"] = {"agent_b": 0.25}
        signals = pd.DataFrame(
            [["2026-08-27", "2026-08-27", "000001", 1, 0.7, 0.0]],
            columns=["signal_date", "trade_date", "ticker", "agent_b_rank", "cnn_probability", "gap_from_previous_close"],
        )
        with self.assertRaisesRegex(ContractError, "신호일보다 뒤"):
            build_shadow_orders(signals, ready)


if __name__ == "__main__":
    unittest.main()
