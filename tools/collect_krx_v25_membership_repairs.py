#!/usr/bin/env python3
"""Archive official KRX [11006] replies for audited 99-member dates."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, importlib.util, json, sys
from datetime import date, datetime, timezone
from getpass import getpass
from pathlib import Path

def load_collector():
    path = Path(__file__).with_name("collect_krx_v25_technical.py")
    spec = importlib.util.spec_from_file_location("krx_v25_technical_collector", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()

def gap_dates(path: Path) -> list[date]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sorted({date.fromisoformat(row["date"]) for row in csv.DictReader(handle) if row.get("count") == "99"})

def parse_archived(collector, path: Path):
    with gzip.open(path, "rb") as handle: frame = collector.parse_csv(handle.read())
    ticker_column = next((column for column in ("ISU_SRT_CD", "종목코드") if column in frame.columns), None)
    if ticker_column is None: ticker_column = next(column for column in frame.columns if "코드" in str(column))
    name_column = next((column for column in ("ISU_ABBRV", "종목명") if column in frame.columns), None)
    frame = frame.rename(columns={ticker_column: "ticker"})
    frame["name"] = frame[name_column].astype(str).str.strip() if name_column else ""
    return frame

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect official KRX [11006] replies for membership repair dates")
    parser.add_argument("--gap-csv", type=Path, default=Path("data/processed/v25_membership_corporate_action_audit/membership_gap_transitions.csv"))
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v25_krx_membership_repairs"))
    parser.add_argument("--reuse-raw", action="store_true", help="Reuse already archived raw replies; do not prompt for Cookie")
    args = parser.parse_args(argv); dates = gap_dates(args.gap_csv)
    if not dates: raise SystemExit("No 99-member dates were found in --gap-csv")
    collector = load_collector(); raw_root = args.output_root / "raw"; client = None
    if not args.reuse_raw:
        cookie = getpass("KRX Cookie (input is not stored or printed): ").strip()
        if not cookie: raise SystemExit("KRX Cookie is required")
        client = collector.KRXClient(cookie)
    args.output_root.mkdir(parents=True, exist_ok=True); output_rows = []; audit_rows = []
    for session in dates:
        raw_path = raw_root / "membership_1034" / f"{session:%Y}" / f"{session:%Y%m%d}.csv.gz"
        try:
            if raw_path.exists(): frame = parse_archived(collector, raw_path)
            elif client is not None: frame = collector.fetch_membership(client, session, raw_root)
            else: raise FileNotFoundError(str(raw_path))
            frame["ticker"] = frame["ticker"].astype(str).str.zfill(6); frame = frame.drop_duplicates("ticker").sort_values("ticker"); count = len(frame)
            status = "OFFICIAL_COUNT_100" if count == 100 else ("OFFICIAL_COUNT_99" if count == 99 else "OFFICIAL_COUNT_OTHER")
            audit_rows.append({"date": session.isoformat(), "status": status, "count": str(count), "detail": "KRX [11006] response archived"})
            output_rows.extend({"date": session.isoformat(), "ticker": row.ticker, "name": row.name, "source": "KRX_11006", "official_count": str(count)} for row in frame.itertuples(index=False))
        except Exception as exc: audit_rows.append({"date": session.isoformat(), "status": "BLOCKED_REQUEST_ERROR", "count": "", "detail": str(exc)})
    with (args.output_root / "membership_repairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "ticker", "name", "source", "official_count"]); writer.writeheader(); writer.writerows(output_rows)
    with (args.output_root / "audit.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "status", "count", "detail"]); writer.writeheader(); writer.writerows(audit_rows)
    files = [{"path": str(path.relative_to(args.output_root)).replace("\\", "/"), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in sorted(args.output_root.rglob("*.csv.gz"))]
    manifest = {"schema_version": "v25-krx-membership-repair-v2", "queried_dates": [day.isoformat() for day in dates], "official_response_dates": sum(row["status"].startswith("OFFICIAL_COUNT_") for row in audit_rows), "official_count_distribution": {str(count): sum(row["count"] == str(count) for row in audit_rows) for count in sorted({row["count"] for row in audit_rows if row["count"]})}, "request_error_dates": sum(row["status"] == "BLOCKED_REQUEST_ERROR" for row in audit_rows), "raw_files": files, "generated_at_utc": datetime.now(timezone.utc).isoformat()}
    (args.output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"queried={len(dates)} official_responses={manifest['official_response_dates']} request_errors={manifest['request_error_dates']}")
    return 0 if manifest["request_error_dates"] == 0 else 2

if __name__ == "__main__": raise SystemExit(main())
