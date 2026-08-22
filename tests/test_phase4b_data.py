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

from kospi100_data.phase4b_partition import FILES, build_phase4b_partition
from kospi100_multifactor.config import load_analysis_config
from kospi100_ranking.data import load_selection_bundle


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gzip(path: Path, text: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(text)


class Phase4BDataTests(unittest.TestCase):
    def _source(self, base: Path) -> Path:
        root = base / "source"
        root.mkdir()
        manifest_rows = []
        for name, column in FILES.items():
            path = root / name
            _gzip(path, f"{column},value\n2017-01-03,1\n2019-01-03,2\n2021-01-04,3\n")
            manifest_rows.append(
                {
                    "file": name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha(path),
                    "date_column": column,
                    "min_date": "2017-01-03",
                    "max_date": "2021-01-04",
                    "rows": 3,
                }
            )
        with (root / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=manifest_rows[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(manifest_rows)
        (root / "partition.json").write_text(
            json.dumps({"role": "phase5_train_validation", "max_date": "2021-12-31", "data_hash": "safe"}),
            encoding="utf-8",
        )
        return root

    def test_builder_creates_deterministic_physical_2018_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self._source(base)
            first = build_phase4b_partition(source, base / "first")
            second = build_phase4b_partition(source, base / "second")
            self.assertEqual(first["data_hash"], second["data_hash"])
            partition = json.loads((base / "first" / "partition.json").read_text(encoding="utf-8"))
            self.assertEqual(partition["role"], "phase4b_train_internal")
            self.assertEqual(partition["max_date"], "2018-12-31")
            self.assertEqual(partition["research_boundary"]["post_2018_rows_in_output"], 0)
            self.assertFalse(partition["research_boundary"]["development_test_input_loaded"])
            for name in FILES:
                frame = pd.read_csv(base / "first" / name)
                self.assertEqual(len(frame), 1)

    def test_manifest_after_2018_is_rejected_before_data_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "partition.json").write_text(
                json.dumps(
                    {
                        "role": "phase4b_train_internal",
                        "max_date": "2018-12-31",
                        "selection": {"post_2021_rows_loaded": 0},
                        "data_hash": "x",
                    }
                ),
                encoding="utf-8",
            )
            with (root / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["file", "bytes", "sha256", "date_column", "min_date", "max_date", "rows"],
                )
                writer.writeheader()
                for name, column in FILES.items():
                    writer.writerow(
                        {
                            "file": name,
                            "bytes": 1,
                            "sha256": "x",
                            "date_column": column,
                            "min_date": "2018-01-02",
                            "max_date": "2019-01-02" if name.startswith("feature") else "2018-12-31",
                            "rows": 1,
                        }
                    )
            config = load_analysis_config(Path("configs/phase4b_multifactor.json"))
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


if __name__ == "__main__":
    unittest.main()
