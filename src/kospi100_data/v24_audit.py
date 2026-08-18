from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


MINUTE_COLUMNS = ["date", "time", "open", "high", "low", "close", "volume", "trading_value"]
PRICE_COLUMNS = ["open", "high", "low", "close"]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    severity: str
    detail: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truth(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "y"})


def _ohlc_valid(frame: pd.DataFrame) -> pd.Series:
    positive = frame[PRICE_COLUMNS].gt(0).all(axis=1)
    ordered = (
        frame["high"].ge(frame["low"])
        & frame["open"].between(frame["low"], frame["high"])
        & frame["close"].between(frame["low"], frame["high"])
    )
    activity = frame[["volume", "trading_value"]].ge(0).all(axis=1)
    return positive & ordered & activity


def _read_csv(path: Path, **kwargs: object) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False, **kwargs)


def audit_core(root: Path) -> tuple[list[Check], dict[str, object]]:
    core = root / "core"
    controls = root / "controls"
    m = _read_csv(core / "kospi100_membership_daily_v24.csv", dtype={"ticker": str})
    f = _read_csv(core / "kospi100_174_full_history_ohlcv_v24.csv", dtype={"ticker": str})
    p = _read_csv(core / "kospi100_feature_price_panel_v24.csv", dtype={"ticker": str})
    i = _read_csv(core / "kospi100_index_ohlcv_v24.csv")
    sm = _read_csv(core / "kospi100_security_master_v24.csv", dtype={"ticker": str})
    ca = _read_csv(core / "kospi100_corporate_action_phase1_production_v24.csv", dtype={"ticker": str})
    adj = _read_csv(controls / "kospi100_ca_feature_adjustments_v24.csv", dtype={"ticker": str})
    resets = _read_csv(controls / "kospi100_ca_feature_resets_v24.csv", dtype={"ticker": str})
    obligations = _read_csv(controls / "kospi100_ca_portfolio_obligations_v24.csv", dtype={"ticker": str})

    for frame in (m, f, p, i):
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")

    checks: list[Check] = []

    def add(name: str, passed: bool, detail: str, severity: str = "BLOCKER") -> None:
        checks.append(Check(name, bool(passed), severity, detail))

    add("membership_unique_key", not m.duplicated(["date", "security_id"]).any(), f"rows={len(m)}")
    counts = m.groupby("date")["security_id"].nunique()
    non100 = counts[counts.ne(100)]
    add(
        "membership_size_documented",
        len(non100) == 26 and non100.eq(99).all(),
        f"dates={len(counts)}, size100={(counts == 100).sum()}, size99={(counts == 99).sum()}",
        "WARNING",
    )
    add("membership_flags", _truth(m["is_member"]).all() and _truth(m["eligible_new_entry"]).all(), "all rows are active/eligible membership rows")
    add("security_master_unique", sm["security_id"].is_unique and sm["ticker"].is_unique, f"rows={len(sm)}")
    add("security_ids_resolve", set(m.security_id).issubset(set(sm.security_id)), f"membership_ids={m.security_id.nunique()}, master_ids={sm.security_id.nunique()}")

    f_valid = _ohlc_valid(f)
    f_tradable = _truth(f["tradable"])
    add("full_history_unique_key", not f.duplicated(["date", "security_id"]).any(), f"rows={len(f)}")
    add("full_history_tradable_ohlc", f_valid[f_tradable].all(), f"tradable_rows={int(f_tradable.sum())}, invalid={int((~f_valid & f_tradable).sum())}")
    add("full_history_invalid_only_nontradable", (~f_valid).eq(~f_tradable).all(), f"invalid={int((~f_valid).sum())}, nontradable={int((~f_tradable).sum())}")

    p_valid = _ohlc_valid(p)
    p_tradable = _truth(p["tradable"])
    p_member = _truth(p["is_member"])
    p_eligible = _truth(p["eligible_new_entry"])
    p_rank = _truth(p["rank_eligible"])
    add("feature_panel_unique_key", not p.duplicated(["date", "security_id"]).any(), f"rows={len(p)}")
    add("feature_panel_tradable_ohlc", p_valid[p_tradable].all(), f"tradable_rows={int(p_tradable.sum())}")
    add("feature_panel_invalid_only_nontradable", (~p_valid).eq(~p_tradable).all(), f"invalid={int((~p_valid).sum())}, nontradable={int((~p_tradable).sum())}")
    expected_rank = p_member & p_eligible & p_tradable
    add("rank_eligibility_exact", p_rank.eq(expected_rank).all(), f"rank_eligible={int(p_rank.sum())}")
    add("pre_entry_warmup_not_ranked", (~p_member & p_rank).sum() == 0, f"warmup_rows={int((~p_member).sum())}")

    member_keys = pd.MultiIndex.from_frame(m[["date", "security_id"]])
    full_member_keys = pd.MultiIndex.from_frame(f.loc[_truth(f["is_member"]), ["date", "security_id"]])
    panel_member_keys = pd.MultiIndex.from_frame(p.loc[p_member, ["date", "security_id"]])
    add("membership_equals_full_member_rows", member_keys.equals(full_member_keys), f"membership={len(member_keys)}, full_member={len(full_member_keys)}")
    add("membership_equals_panel_member_rows", member_keys.equals(panel_member_keys), f"membership={len(member_keys)}, panel_member={len(panel_member_keys)}")

    add("index_unique_dates", i["date"].notna().all() and i["date"].is_unique, f"rows={len(i)}")
    add("index_ohlc", _ohlc_valid(i.rename(columns={"volume_thousand_shares": "volume", "trading_value_million_krw": "trading_value"})).all(), f"rows={len(i)}")
    add("index_membership_calendar_alignment", set(i.date) == set(m.date), f"index_dates={i.date.nunique()}, membership_dates={m.date.nunique()}")

    ca_ids = set(ca.canonical_event_id)
    add("ca_unique_ids", ca.canonical_event_id.is_unique, f"events={len(ca)}")
    add("ca_controls_complete", ca_ids == set(obligations.canonical_event_id), f"events={len(ca_ids)}, obligations={len(obligations)}")
    add("ca_partition_complete", ca_ids == set(adj.canonical_event_id) | set(resets.canonical_event_id) and set(adj.canonical_event_id).isdisjoint(set(resets.canonical_event_id)), f"adjustments={len(adj)}, resets={len(resets)}")
    add("ca_adjustments_have_factors", adj[["feature_boundary_date", "share_multiplier", "price_multiplier"]].notna().all().all(), f"rows={len(adj)}")
    add("ca_resets_have_boundary", resets["feature_boundary_date"].notna().all(), f"rows={len(resets)}")

    stats = {
        "membership": {"rows": len(m), "dates": int(m.date.nunique()), "securities": int(m.security_id.nunique()), "date_min": str(m.date.min().date()), "date_max": str(m.date.max().date()), "size_99_dates": int((counts == 99).sum())},
        "full_history": {"rows": len(f), "securities": int(f.security_id.nunique()), "date_min": str(f.date.min().date()), "date_max": str(f.date.max().date()), "nontradable_rows": int((~f_tradable).sum())},
        "feature_panel": {"rows": len(p), "rank_eligible": int(p_rank.sum()), "warmup_rows": int((~p_member).sum())},
        "index": {"rows": len(i), "date_min": str(i.date.min().date()), "date_max": str(i.date.max().date())},
        "corporate_actions": {"events": len(ca), "mechanical_adjustments": len(adj), "feature_resets": len(resets)},
    }
    return checks, stats


def audit_manifest(root: Path) -> tuple[list[Check], dict[str, object]]:
    manifest = _read_csv(root / "MANIFEST_V24.csv")
    checks: list[Check] = []
    missing: list[str] = []
    mismatch: list[str] = []
    for row in manifest.to_dict("records"):
        rel = str(row.get("path") or row.get("relative_path") or row.get("file") or "")
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        expected_size = row.get("size_bytes")
        if pd.notna(expected_size) and int(expected_size) != path.stat().st_size:
            mismatch.append(f"{rel}:size")
        expected_hash = str(row.get("sha256", ""))
        if expected_hash and expected_hash != "nan" and expected_hash != sha256_file(path):
            mismatch.append(f"{rel}:sha256")
    expected_missing = {"intraday/raw_archives/1m.zip", "intraday/raw_archives/5m.zip"}
    checks.append(Check("manifest_core_files", not mismatch and set(missing) == expected_missing, "WARNING", f"missing_split_replaced={missing}, mismatches={mismatch}"))
    return checks, {"manifest_rows": len(manifest), "missing_expected_monolithic_archives": missing, "mismatches": mismatch}


def _minute_code(path: Path) -> str:
    return path.name.split("_", 1)[0]


def audit_minute_file(path: Path) -> tuple[dict[str, object], pd.DataFrame]:
    try:
        with gzip.open(path, "rb") as handle:
            while handle.read(1024 * 1024):
                pass
        frame = pd.read_csv(path)
        schema_ok = list(frame.columns) == MINUTE_COLUMNS
        required_ok = frame[MINUTE_COLUMNS].notna().all().all() if schema_ok else False
        key_unique = not frame.duplicated(["date", "time"]).any() if schema_ok else False
        values_ok = _ohlc_valid(frame).all() if schema_ok else False
        sorted_ok = frame[["date", "time"]].equals(frame[["date", "time"]].sort_values(["date", "time"]).reset_index(drop=True))
        summary = {
            "code": _minute_code(path),
            "path": str(path),
            "rows": len(frame),
            "date_min": int(frame.date.min()) if len(frame) else None,
            "date_max": int(frame.date.max()) if len(frame) else None,
            "schema_ok": bool(schema_ok),
            "required_ok": bool(required_ok),
            "unique_key": bool(key_unique),
            "values_ok": bool(values_ok),
            "sorted_ok": bool(sorted_ok),
            "gzip_ok": True,
        }
        return summary, frame
    except Exception as exc:  # surfaced in the machine-readable audit report
        return {"code": _minute_code(path), "path": str(path), "rows": 0, "gzip_ok": False, "error": repr(exc)}, pd.DataFrame()


def _aggregate_1m(frame: pd.DataFrame) -> pd.DataFrame:
    hour = frame["time"] // 100
    minute = frame["time"] % 100
    total = hour * 60 + minute
    bucket = ((total + 4) // 5) * 5
    frame = frame.assign(bucket_time=(bucket // 60) * 100 + bucket % 60)
    return (
        frame.groupby(["date", "bucket_time"], sort=True, as_index=False)
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"), trading_value=("trading_value", "sum"))
        .rename(columns={"bucket_time": "time"})
    )


def audit_intraday(root: Path) -> tuple[list[Check], dict[str, object], list[dict[str, object]]]:
    files_1m = sorted((root / "intraday" / "1m").rglob("*.csv.gz"), key=_minute_code)
    files_5m = sorted((root / "intraday" / "5m").rglob("*.csv.gz"), key=_minute_code)
    map_5m = {_minute_code(path): path for path in files_5m}
    file_rows: list[dict[str, object]] = []
    reconciliation: list[dict[str, object]] = []
    total_1m = total_5m = 0
    all_files_ok = True
    all_exact = True

    for path_1m in files_1m:
        code = _minute_code(path_1m)
        summary_1m, one = audit_minute_file(path_1m)
        summary_1m["interval"] = "1m"
        file_rows.append(summary_1m)
        total_1m += int(summary_1m["rows"])
        all_files_ok &= all(summary_1m.get(key, False) for key in ("gzip_ok", "schema_ok", "required_ok", "unique_key", "values_ok", "sorted_ok"))

        path_5m = map_5m.get(code)
        if path_5m is None:
            reconciliation.append({"code": code, "exact": False, "reason": "missing_5m_file"})
            all_exact = False
            continue
        summary_5m, five = audit_minute_file(path_5m)
        summary_5m["interval"] = "5m"
        file_rows.append(summary_5m)
        total_5m += int(summary_5m["rows"])
        all_files_ok &= all(summary_5m.get(key, False) for key in ("gzip_ok", "schema_ok", "required_ok", "unique_key", "values_ok", "sorted_ok"))
        if one.empty or five.empty:
            reconciliation.append({"code": code, "exact": False, "reason": "unreadable_or_empty"})
            all_exact = False
            continue

        overlap_start = max(int(one.date.min()), int(five.date.min()))
        overlap_end = min(int(one.date.max()), int(five.date.max()))
        one_overlap = one[one.date.between(overlap_start, overlap_end)]
        five_overlap = five[five.date.between(overlap_start, overlap_end)]
        agg = _aggregate_1m(one_overlap)
        merged = agg.merge(five_overlap, on=["date", "time"], how="outer", suffixes=("_1m", "_5m"), indicator=True)
        exact = merged["_merge"].eq("both").all()
        mismatches: dict[str, int] = {}
        for column in PRICE_COLUMNS + ["volume", "trading_value"]:
            bad = merged[f"{column}_1m"].ne(merged[f"{column}_5m"]) | merged[f"{column}_1m"].isna() | merged[f"{column}_5m"].isna()
            mismatches[column] = int(bad.sum())
            exact &= not bad.any()
        reconciliation.append({
            "code": code,
            "overlap_start": overlap_start,
            "overlap_end": overlap_end,
            "aggregated_1m_rows": len(agg),
            "native_5m_rows": len(five_overlap),
            "key_mismatches": int(merged["_merge"].ne("both").sum()),
            **{f"{column}_mismatches": count for column, count in mismatches.items()},
            "exact": bool(exact),
        })
        all_exact &= bool(exact)

    extra_5m = sorted(set(map_5m) - {_minute_code(path) for path in files_1m})
    checks = [
        Check("intraday_file_count", len(files_1m) == 159 and len(files_5m) == 159, "BLOCKER", f"1m={len(files_1m)}, 5m={len(files_5m)}"),
        Check("intraday_file_integrity", all_files_ok, "BLOCKER", f"validated={len(file_rows)}/318"),
        Check("intraday_instrument_sets", not extra_5m and set(map_5m) == {_minute_code(path) for path in files_1m}, "BLOCKER", f"extra_5m={extra_5m}"),
        Check("intraday_exact_1m_to_5m", all_exact and len(reconciliation) == 159, "BLOCKER", f"exact={sum(bool(row.get('exact')) for row in reconciliation)}/159"),
    ]
    stats = {
        "files_1m": len(files_1m), "files_5m": len(files_5m), "rows_1m": total_1m, "rows_5m": total_5m,
        "reconciled_exact": sum(bool(row.get("exact")) for row in reconciliation),
    }
    return checks, stats, file_rows + [{"interval": "1m_to_5m", **row} for row in reconciliation]


def run(root: Path, output_dir: Path) -> dict[str, object]:
    checks: list[Check] = []
    manifest_checks, manifest_stats = audit_manifest(root)
    checks.extend(manifest_checks)
    core_checks, core_stats = audit_core(root)
    checks.extend(core_checks)
    minute_checks, minute_stats, minute_rows = audit_intraday(root)
    checks.extend(minute_checks)
    blockers = [check for check in checks if not check.passed and check.severity == "BLOCKER"]
    result = {
        "phase": 1,
        "package_version": "v24",
        "status": "PASS" if not blockers else "FAIL",
        "checks": [asdict(check) for check in checks],
        "stats": {"manifest": manifest_stats, "core": core_stats, "intraday": minute_stats},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase1_v24_independent_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame([asdict(check) for check in checks]).to_csv(output_dir / "phase1_v24_checks.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(minute_rows).to_csv(output_dir / "phase1_v24_intraday_checks.csv", index=False, encoding="utf-8-sig")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent Phase 1 audit for the KOSPI100 v24 production package")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.output_dir)
    print(json.dumps({"status": result["status"], "stats": result["stats"]}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
