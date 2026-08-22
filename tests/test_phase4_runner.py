import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from kospi100_features.runner import OUTPUT_FILES, REQUIRED_DATA_FILES, load_phase4_bundle, run_phase4
from kospi100_features.config import load_config


CONFIG_PATH = Path("configs/phase4_revalidation_20260819.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_gzip_csv(frame: pd.DataFrame, path: Path) -> None:
    data = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(data)


def _synthetic_root(root: Path, *, dates: pd.DatetimeIndex | None = None) -> Path:
    data_root = root / "phase4_train_validation"
    data_root.mkdir()
    if dates is None:
        dates = pd.bdate_range("2017-01-02", periods=600)
    securities = [f"S{index:03d}" for index in range(35)]
    index_frame = pd.DataFrame(
        {"date": dates, "open": np.linspace(100.0, 130.0, len(dates)), "close": np.linspace(100.0, 135.0, len(dates))}
    )
    panel_rows = []
    for security_index, security in enumerate(securities):
        price = np.linspace(10.0 + security_index, 20.0 + security_index, len(dates))
        for day, close in zip(dates, price):
            panel_rows.append(
                {
                    "date": day,
                    "security_id": security,
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "feature_volume": 1000.0 + security_index,
                    "feature_trading_value": close * (1000.0 + security_index),
                    "is_member": True,
                    "eligible_new_entry": True,
                    "tradable": True,
                    "rank_eligible": True,
                }
            )
    panel = pd.DataFrame(panel_rows)
    full = panel[["date", "security_id", "open", "is_member", "eligible_new_entry", "tradable", "rank_eligible"]].copy()
    actions = pd.DataFrame(
        columns=[
            "security_id", "canonical_event_id", "feature_handling", "feature_boundary_date",
            "price_multiplier", "share_multiplier", "first_filing_date", "portfolio_terms_status",
        ]
    )
    frames = {
        "feature_price_panel.csv.gz": panel,
        "full_history_ohlcv.csv.gz": full,
        "index_ohlcv.csv.gz": index_frame,
        "corporate_actions.csv.gz": actions,
    }
    manifest_rows = []
    for name, frame in frames.items():
        path = data_root / name
        _write_gzip_csv(frame, path)
        date_column = "feature_boundary_date" if name == "corporate_actions.csv.gz" else "date"
        parsed = pd.to_datetime(frame[date_column], errors="coerce").dropna()
        manifest_rows.append(
            {
                "file": name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "date_column": date_column,
                "min_date": parsed.min().date().isoformat() if not parsed.empty else "",
                "max_date": parsed.max().date().isoformat() if not parsed.empty else "",
                "rows": len(frame),
            }
        )
    pd.DataFrame(manifest_rows).sort_values("file").to_csv(data_root / "manifest.csv", index=False, lineterminator="\n")
    (data_root / "partition.json").write_text(
        json.dumps({"role": "phase4_train_validation", "max_date": "2021-12-31"}), encoding="utf-8"
    )
    return data_root


def _config_for_root(root: Path, data_root: Path) -> Path:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["data_root"] = str(data_root)
    config = root / "config.json"
    config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return config


class Phase4RunnerTests(unittest.TestCase):
    def test_runner_outputs_hashes_and_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = _synthetic_root(root)
            config = _config_for_root(root, data_root)
            first = root / "first"
            second = root / "second"
            run_phase4(config, first)
            run_phase4(config, second)

            expected = set(OUTPUT_FILES) | {"manifest.json"}
            self.assertEqual({path.name for path in first.iterdir()}, expected)
            for name in expected:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["files"].items():
                self.assertEqual(_sha256(first / name), digest)
            audit = json.loads((first / "data_audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["experiment_id"], "P4-REVALIDATION-20260819-001")
            self.assertEqual(audit["partition_role"], "phase4_train_validation")
            self.assertEqual(audit["partition_max_date"], "2021-12-31")
            self.assertEqual(audit["source_hash"], manifest["source_hash"])
            self.assertEqual(audit["config_hash"], manifest["config_hash"])
            self.assertFalse(audit["final_oos_accessed"])
            self.assertFalse(audit["development_test_input_loaded"])
            self.assertEqual(audit["development_test_rows_loaded"], 0)
            self.assertEqual(audit["development_test_rows_evaluated"], 0)
            self.assertEqual(audit["development_test_rows_calculated"], 0)
            self.assertEqual(audit["development_test_rows_selected"], 0)
            self.assertFalse(audit["filter_applied_after_load"])
            self.assertLessEqual(audit["maximum_loaded_date"], "2021-12-31")
            self.assertEqual(audit["maximum_calculation_input_date"], audit["maximum_loaded_date"])
            self.assertEqual({item["file"] for item in audit["input_files"]}, set(REQUIRED_DATA_FILES))
            self.assertTrue(all(not item["filter_applied_after_load"] for item in audit["input_files"]))
            self.assertTrue(all(item["loaded_rows"] == item["rows_before_filtering"] for item in audit["input_files"]))

    def test_integrated_partition_is_rejected_before_data_file_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = _synthetic_root(root)
            (data_root / "partition.json").write_text(
                json.dumps({"role": "development", "max_date": "2023-12-31"}), encoding="utf-8"
            )
            config = load_config(_config_for_root(root, data_root))
            with patch("kospi100_features.runner._read_input_frame") as reader:
                with self.assertRaises(PermissionError):
                    load_phase4_bundle(config)
            reader.assert_not_called()

    def test_post_2021_rows_in_forged_partition_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dates = pd.bdate_range("2021-12-20", periods=20)
            data_root = _synthetic_root(root, dates=dates)
            config = load_config(_config_for_root(root, data_root))
            with self.assertRaises(PermissionError):
                load_phase4_bundle(config)

    def test_reader_opens_only_allowlisted_partition_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = _synthetic_root(root)
            config = load_config(_config_for_root(root, data_root))
            calls: list[Path] = []
            original = pd.read_csv

            def recording_reader(path: Path) -> pd.DataFrame:
                calls.append(Path(path).resolve())
                return original(path, low_memory=False)

            with patch("kospi100_features.runner._read_input_frame", side_effect=recording_reader):
                bundle = load_phase4_bundle(config)
            self.assertFalse(bundle.audit["final_oos_accessed"])
            expected = {(data_root / name).resolve() for name in REQUIRED_DATA_FILES}
            self.assertEqual(set(calls), expected)

    def test_package_import_and_registry_cli_shape(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import kospi100_features; print(kospi100_features.run_phase4.__name__)"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("run_phase4", result.stdout)
        help_result = subprocess.run(
            [sys.executable, "-m", "kospi100_features.cli", "run", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--config", help_result.stdout)
        self.assertIn("--output", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
