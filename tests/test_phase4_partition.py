from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kospi100_data.phase4_partition import REQUIRED_FILES, build_phase4_partition, sha256_file


def _write_gzip(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fieldnames, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def _source(root: Path) -> Path:
    source = root / "development"
    source.mkdir()
    common_rows = [
        {"date": "2021-12-30", "value": "keep-a"},
        {"date": "2021-12-31", "value": "keep-b"},
        {"date": "2022-01-03", "value": "discard"},
    ]
    for name, date_column in REQUIRED_FILES.items():
        rows = common_rows
        if date_column != "date":
            rows = [{date_column: row["date"], "value": row["value"]} for row in common_rows]
        _write_gzip(source / name, [date_column, "value"], rows)
    manifest_rows = [
        {"file": name, "bytes": (source / name).stat().st_size, "sha256": sha256_file(source / name)}
        for name in sorted(REQUIRED_FILES)
    ]
    with (source / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)
    (source / "partition.json").write_text(
        json.dumps({"role": "development", "max_date": "2023-12-31"}) + "\n",
        encoding="utf-8",
    )
    return source


class Phase4PartitionTests(unittest.TestCase):
    def test_builds_only_registered_rows_and_extended_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _source(root)
            output = root / "phase4_train_validation_2021"
            result = build_phase4_partition(source, output)
            self.assertEqual("PASS", result["status"])
            self.assertEqual("2021-12-31", result["maximum_date"])

            with (output / "manifest.csv").open("r", encoding="utf-8", newline="") as handle:
                manifest = list(csv.DictReader(handle))
            self.assertEqual(set(REQUIRED_FILES), {row["file"] for row in manifest})
            self.assertTrue(all(row["rows"] == "2" for row in manifest))
            self.assertTrue(all(row["max_date"] == "2021-12-31" for row in manifest))
            for row in manifest:
                with gzip.open(output / row["file"], "rt", encoding="utf-8", newline="") as handle:
                    values = list(csv.DictReader(handle))
                self.assertEqual(["keep-a", "keep-b"], [value["value"] for value in values])
                self.assertEqual(str((output / row["file"]).stat().st_size), row["bytes"])
                self.assertEqual(sha256_file(output / row["file"]), row["sha256"])

            partition = json.loads((output / "partition.json").read_text(encoding="utf-8"))
            material = "\n".join(
                f"{row['file']}:{row['sha256']}" for row in sorted(manifest, key=lambda row: row["file"])
            )
            self.assertEqual(hashlib.sha256(material.encode("utf-8")).hexdigest(), partition["data_hash"])
            self.assertFalse(partition["selection"]["excluded_rows_retained_or_aggregated"])

    def test_build_is_byte_deterministic_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _source(root)
            first = root / "first"
            second = root / "second"
            build_phase4_partition(source, first)
            build_phase4_partition(source, second)
            names = [*REQUIRED_FILES, "manifest.csv", "partition.json"]
            self.assertTrue(all((first / name).read_bytes() == (second / name).read_bytes() for name in names))
            with self.assertRaises(FileExistsError):
                build_phase4_partition(source, first)

    def test_source_hash_mismatch_and_protected_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _source(root)
            manifest_path = source / "manifest.csv"
            with manifest_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["sha256"] = "0" * 64
            with manifest_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256"], lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "hash 불일치"):
                build_phase4_partition(source, root / "output")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _source(root)
            with self.assertRaises(PermissionError):
                build_phase4_partition(source, root / "sealed" / "final_oos_v24" / "output")


if __name__ == "__main__":
    unittest.main()
