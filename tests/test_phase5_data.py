from __future__ import annotations

import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from kospi100_data.phase5_partition import build_phase5_selection_partition
from kospi100_ranking.config import load_config
from kospi100_ranking.data import load_selection_bundle


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_gzip(path: Path, text: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(text)


class Phase5DataTests(unittest.TestCase):
    def test_manifest_crossing_boundary_is_rejected_before_data_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "partition.json").write_text(
                json.dumps(
                    {
                        "role": "phase5_train_validation",
                        "max_date": "2021-12-31",
                        "selection": {"post_2021_rows_loaded": 0},
                    }
                ),
                encoding="utf-8",
            )
            with (root / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256", "date_column", "min_date", "max_date", "rows"])
                writer.writeheader()
                for name, column in {
                    "feature_price_panel.csv.gz": "date",
                    "full_history_ohlcv.csv.gz": "date",
                    "index_ohlcv.csv.gz": "date",
                    "corporate_actions.csv.gz": "feature_boundary_date",
                    "removal_orders.csv.gz": "execution_date",
                }.items():
                    writer.writerow({"file": name, "bytes": 1, "sha256": "x", "date_column": column, "min_date": "2021-01-01", "max_date": "2022-01-03" if name.startswith("feature") else "2021-12-31", "rows": 1})
            config = load_config(Path("configs/phase5_ranking.json"))
            object.__setattr__(config, "data_root", root)
            original = pd.read_csv
            data_reads: list[str] = []

            def guarded(path, *args, **kwargs):
                if str(path).endswith("manifest.csv"):
                    return original(path, *args, **kwargs)
                data_reads.append(str(path))
                return original(path, *args, **kwargs)

            with patch("kospi100_ranking.data.pd.read_csv", side_effect=guarded):
                with self.assertRaises(PermissionError):
                    load_selection_bundle(config)
            self.assertEqual(data_reads, [])

    def test_partition_builder_uses_only_safe_phase4_and_safe_phase3_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "phase4"
            source.mkdir()
            rows = []
            for name, column in {
                "feature_price_panel.csv.gz": "date",
                "full_history_ohlcv.csv.gz": "date",
                "index_ohlcv.csv.gz": "date",
                "corporate_actions.csv.gz": "feature_boundary_date",
            }.items():
                path = source / name
                write_gzip(path, f"{column},value\n2021-01-04,1\n")
                rows.append({"file": name, "bytes": path.stat().st_size, "sha256": sha256(path), "date_column": column, "min_date": "2021-01-04", "max_date": "2021-01-04", "rows": 1})
            with (source / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
                writer.writeheader(); writer.writerows(rows)
            (source / "partition.json").write_text(
                json.dumps({"role": "phase4_train_validation", "max_date": "2021-12-31", "data_hash": "safe"}),
                encoding="utf-8",
            )
            headers = "order_id,signal_date,execute_date,security_id,reason\n"
            train = base / "train.csv"; validation = base / "validation.csv"
            train.write_text(headers + "P3:REMOVAL_EXIT:000001:01,2020-01-02,2020-01-03,KRX_COMMON:000001,UNIVERSE_REMOVAL_EXIT\n", encoding="utf-8")
            validation.write_text(headers + "P3:REMOVAL_EXIT:000002:01,2021-01-04,2021-01-05,KRX_COMMON:000002,UNIVERSE_REMOVAL_EXIT\n", encoding="utf-8")
            output = base / "phase5"
            first = build_phase5_selection_partition(source, train, validation, output)
            self.assertEqual(first["maximum_date"], "2021-12-31")
            partition = json.loads((output / "partition.json").read_text(encoding="utf-8"))
            self.assertEqual(partition["role"], "phase5_train_validation")
            self.assertEqual(partition["selection"]["post_2021_rows_loaded"], 0)
            self.assertFalse(partition["selection"]["development_test_partition_created"])
            controls = pd.read_csv(output / "removal_orders.csv.gz")
            self.assertEqual(len(controls), 2)
            self.assertLessEqual(controls["execution_date"].max(), "2021-12-31")


if __name__ == "__main__":
    unittest.main()
