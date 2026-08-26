import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


TOOL = Path(__file__).resolve().parents[1] / "tools" / "run_phase4c_market_reference_audit.py"
SPEC = importlib.util.spec_from_file_location("phase4c_market_reference_audit", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Phase4CMarketReferenceAuditTests(unittest.TestCase):
    def test_config_is_frozen_to_internal_period_and_no_promotion(self):
        config = MODULE.load_config(Path("configs/phase4c_market_reference_audit.json"))
        self.assertEqual(config["maximum_permitted_date"], "2018-12-31")
        self.assertEqual(len(config["reference_features"]) * len(MODULE.STOCK_FEATURES), 84)
        self.assertEqual(config["promotion"], "NO_PROMOTION_IN_PHASE4C_AUDIT_ONLY")

    def test_reference_manifest_after_2018_is_rejected_before_reader(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(json.dumps({"schema_version": "phase1b-market-reference-v1", "role": "reference_only_not_universe", "max_loaded_date": "2019-01-02", "post_2023_files_loaded": False, "output_sha256": "x"}), encoding="utf-8")
            with patch.object(MODULE.pd, "read_csv") as reader:
                with self.assertRaises(PermissionError):
                    MODULE.load_reference(root)
            reader.assert_not_called()

    def test_standardization_uses_train_only(self):
        transformed, state = MODULE.standardize_from_train(pd.Series([1.0, 3.0]), pd.Series([101.0]))
        self.assertEqual(state, {"train_mean": 2.0, "train_std": 1.0})
        self.assertEqual(float(transformed.iloc[0]), 99.0)

