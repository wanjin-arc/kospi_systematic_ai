#!/usr/bin/env python3
"""Build a separate Phase-1-shaped v25 candidate from KRX raw files.

This is an auditable conversion, not a release.  It never edits v24/raw data,
does not infer corporate-action terms, and marks the output blocked until the
fail-closed corporate-action audit is resolved.
"""
from __future__ import annotations

import argparse, csv, gzip, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()

def rows(path: Path):
    with gzip.open(path, "rt", encoding="cp949", errors="replace", newline="") as f:
        yield from csv.reader(f)

def number(value: str) -> str:
    return value.strip().replace(",", "")

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--krx-root", type=Path, required=True)
    p.add_argument("--membership", type=Path, required=True)
    p.add_argument("--corporate-audit-manifest", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    args = p.parse_args(argv)
    if "final_oos" in str(args.krx_root).lower() or "sealed" in str(args.krx_root).lower():
        raise ValueError("Protected OOS path is forbidden")
    ca = json.loads(args.corporate_audit_manifest.read_text(encoding="utf-8"))
    if ca.get("automatic_adjustments_emitted") != 0 or ca.get("resolution_status_counts", {}).get("UNRESOLVED_BLOCK_IF_IN_UNIVERSE", 0):
        blocked_reason = "CORPORATE_ACTIONS_UNRESOLVED"
    else:
        blocked_reason = ""
    membership_hash = sha256(args.membership)
    args.output_root.mkdir(parents=True, exist_ok=True)
    for name in ("ohlcv_raw.csv", "index_ohlcv_raw.csv", "universe_membership.csv", "symbol_master.csv", "trading_calendar.csv"):
        (args.output_root / name).write_text("", encoding="utf-8")
    ohlcv = args.output_root / "ohlcv_raw.csv"
    index_out = args.output_root / "index_ohlcv_raw.csv"
    symbol_out = args.output_root / "symbol_master.csv"
    cal_out = args.output_root / "trading_calendar.csv"
    oheaders = ["trade_date","symbol_id","symbol","open","high","low","close","volume","traded_value","market_status","source_file","source_sha256"]
    iheaders = ["trade_date","index_code","index_name","open","high","low","close","volume","traded_value","source_file","source_sha256"]
    with ohlcv.open("w", encoding="utf-8", newline="") as fo, index_out.open("w", encoding="utf-8", newline="") as fi:
        ow, iw = csv.DictWriter(fo, fieldnames=oheaders), csv.DictWriter(fi, fieldnames=iheaders)
        ow.writeheader(); iw.writeheader()
        market_dates = set()
        names: dict[str, str] = {}
        first: dict[str, str] = {}; last: dict[str, str] = {}
        market_files = sorted((args.krx_root / "raw" / "market_stk").glob("*/*.csv.gz"))
        for path in market_files:
            day = path.stem.split(".")[0]
            if len(day) != 8: continue
            iso = f"{day[:4]}-{day[4:6]}-{day[6:8]}"; digest = sha256(path); market_dates.add(iso)
            for n, row in enumerate(rows(path)):
                if n == 0: continue
                if len(row) < 10 or not row[0].strip().isdigit(): continue
                ticker = row[0].strip().zfill(6); name = row[1].strip()
                names.setdefault(ticker, name); first.setdefault(ticker, iso); last[ticker] = iso
                ow.writerow({"trade_date": iso, "symbol_id": f"KRX_COMMON:{ticker}", "symbol": ticker, "open": number(row[5]), "high": number(row[6]), "low": number(row[7]), "close": number(row[2]), "volume": number(row[8]), "traded_value": number(row[9]), "market_status": "OBSERVED", "source_file": str(path).replace("\\", "/"), "source_sha256": digest})
        ipath = next(iter((args.krx_root / "raw" / "index_1001").glob("*.csv.gz")), None)
        if ipath is None: raise FileNotFoundError("KOSPI index raw partition is missing")
        digest = sha256(ipath)
        for n, row in enumerate(rows(ipath)):
            if n == 0: continue
            if len(row) < 9: continue
            day = row[0].strip().replace("/", "-")
            iw.writerow({"trade_date": day, "index_code": "1001", "index_name": "KOSPI", "open": number(row[4]), "high": number(row[5]), "low": number(row[6]), "close": number(row[1]), "volume": number(row[7]), "traded_value": number(row[8]), "source_file": str(ipath).replace("\\", "/"), "source_sha256": digest})
    with symbol_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol_id","symbol","isin","company_name","valid_from","valid_to","listing_date","delisting_date","source_file","source_sha256"]); w.writeheader()
        for ticker in sorted(names): w.writerow({"symbol_id": f"KRX_COMMON:{ticker}", "symbol": ticker, "isin": "", "company_name": names[ticker], "valid_from": first[ticker], "valid_to": last[ticker], "listing_date": "", "delisting_date": "", "source_file": "v25 KRX market partitions", "source_sha256": ""})
    membership_out = args.output_root / "universe_membership.csv"
    with args.membership.open("r", encoding="utf-8-sig", newline="") as source, membership_out.open("w", encoding="utf-8", newline="") as target:
        reader = csv.DictReader(source)
        w = csv.DictWriter(target, fieldnames=["index_name","index_code","symbol_id","symbol","company_name","valid_from","valid_to","announcement_at","effective_date","source_file","source_sha256","retrieved_at_kst"]); w.writeheader()
        for row in reader:
            if row.get("is_member", "").strip().lower() not in {"true", "1", "yes"}: continue
            day = row.get("date", ""); ticker = row.get("ticker", "").zfill(6)
            w.writerow({"index_name": "KOSPI 100", "index_code": "KOSPI100", "symbol_id": f"KRX_COMMON:{ticker}", "symbol": ticker, "company_name": row.get("name", ""), "valid_from": day, "valid_to": day, "announcement_at": "", "effective_date": day, "source_file": str(args.membership).replace("\\", "/"), "source_sha256": membership_hash, "retrieved_at_kst": ""})
    with cal_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["trade_date","is_trading_day","market_open_kst","market_close_kst","is_early_close","source_file","source_sha256"]); w.writeheader()
        for day in sorted(market_dates): w.writerow({"trade_date": day, "is_trading_day": "True", "market_open_kst": "", "market_close_kst": "", "is_early_close": "", "source_file": "v25 KRX market partitions", "source_sha256": ""})
    (args.output_root / "corporate_actions.csv").write_text("symbol_id,symbol,action_type,announcement_at,effective_date,share_factor_numerator,share_factor_denominator,cash_amount,currency,source_file,source_sha256\n", encoding="utf-8")
    (args.output_root / "suspensions.csv").write_text("symbol_id,symbol,suspended_from,suspended_to,reason,source_file,source_sha256\n", encoding="utf-8")
    manifest = {"schema_version": "v25-phase1-candidate-v1", "status": "BLOCKED", "blocked_reason": blocked_reason or "NONE", "allow_model_use": False, "input_krx_root": str(args.krx_root), "input_membership": str(args.membership), "membership_sha256": membership_hash, "corporate_audit_manifest": str(args.corporate_audit_manifest), "corporate_audit_manifest_sha256": sha256(args.corporate_audit_manifest), "note": "Phase-1-shaped conversion only; unresolved corporate actions and missing historical identity terms prevent release", "generated_at_utc": datetime.now(timezone.utc).isoformat()}
    (args.output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "blocked_reason": blocked_reason, "output_root": str(args.output_root)}, ensure_ascii=False))
    return 2 if blocked_reason else 0

if __name__ == "__main__": raise SystemExit(main())
