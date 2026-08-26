#!/usr/bin/env python3
"""동결 identity·canonical accounts·KRX 시가총액으로 일별 20 Factor 패널을 만든다."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from kospi200_fundamental import FACTOR_IDS, compute_factors, cross_sectional_transform
from kospi200_fundamental.panel import REPORT_QUARTER, trailing_values


FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def guard_path(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def load_identity_status(path: Path) -> dict[tuple[str, str], bool]:
    result: dict[tuple[str, str], bool] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result[(str(row["ticker"]).zfill(6), str(row["membership_name"]))] = row["model_eligible"] == "true"
    return result


def load_canonical(path: Path) -> dict[str, list[dict[str, object]]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (str(row["ticker"]).zfill(6), str(row["source_file"]))
            event = grouped.setdefault(key, {
                "ticker": key[0], "available_from": str(row["available_from"]),
                "year": int(row["business_year"]), "quarter": REPORT_QUARTER[str(row["report_code"])], "values": {},
            })
            try:
                event["values"][str(row["canonical_account"])] = float(row["amount"])
            except ValueError:
                continue
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in grouped.values():
        result[str(event["ticker"])].append(event)
    for events in result.values():
        events.sort(key=lambda item: (str(item["available_from"]), int(item["year"]), int(item["quarter"])))
    return result


def read_market(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, compression="gzip", encoding="cp949", dtype=str, keep_default_na=False)
    ticker_col = next(column for column in ("종목코드", "ISU_SRT_CD") if column in frame.columns)
    cap_col = next(column for column in ("시가총액", "MKTCAP") if column in frame.columns)
    close_col = next(column for column in ("종가", "TDD_CLSPRC") if column in frame.columns)
    volume_col = next(column for column in ("거래량", "ACC_TRDVOL") if column in frame.columns)
    output = frame[[ticker_col, cap_col, close_col, volume_col]].copy()
    output.columns = ["ticker", "market_cap", "close", "volume"]
    output["ticker"] = output["ticker"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)
    for column in ("market_cap", "close", "volume"):
        output[column] = pd.to_numeric(output[column].astype(str).str.replace(",", "", regex=False), errors="coerce")
    return output.drop_duplicates("ticker").set_index("ticker")


def build(canonical_path: Path, identity_path: Path, membership_root: Path, market_root: Path, factor_contract: Path, output_root: Path, minimum_year: int = 2015) -> dict[str, object]:
    for path in (canonical_path, identity_path, membership_root, market_root, factor_contract, output_root):
        guard_path(path)
    identities = load_identity_status(identity_path)
    events_by_ticker = load_canonical(canonical_path)
    active: dict[str, dict[tuple[int, int], dict[str, float]]] = defaultdict(dict)
    positions: dict[str, int] = defaultdict(int)
    rows: list[dict[str, object]] = []
    membership_paths = sorted(path for path in membership_root.rglob("*.csv") if f"{minimum_year:04d}" <= path.stem[:4] <= "2023")
    if not membership_paths:
        raise FileNotFoundError(f"{minimum_year}~2023 KOSPI 200 membership 세션이 없습니다.")
    market_files_loaded = 0
    loaded_market_paths: list[Path] = []
    for membership_path in membership_paths:
        day = membership_path.stem
        date_text = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        market_path = market_root / day[:4] / f"{day}.csv.gz"
        if not market_path.exists():
            continue
        membership = pd.read_csv(membership_path, dtype=str, keep_default_na=False)
        market = read_market(market_path)
        market_files_loaded += 1
        loaded_market_paths.append(market_path)
        for item in membership.itertuples(index=False):
            ticker, name = str(item.ticker).zfill(6), str(item.name)
            if not identities.get((ticker, name), False):
                continue
            events = events_by_ticker.get(ticker, [])
            position = positions[ticker]
            while position < len(events) and str(events[position]["available_from"]) <= date_text:
                event = events[position]
                active[ticker][(int(event["year"]), int(event["quarter"]))] = dict(event["values"])
                position += 1
            positions[ticker] = position
            statements = active.get(ticker, {})
            if not statements or ticker not in market.index:
                continue
            year, quarter = max(statements)
            current = trailing_values(statements, year, quarter)
            prior = trailing_values(statements, year - 1, quarter) if (year - 1, quarter) in statements else {}
            current["market_cap"] = float(market.at[ticker, "market_cap"])
            factors = compute_factors(current, prior)
            row: dict[str, object] = {
                "date": date_text, "ticker": ticker, "membership_name": name,
                "statement_year": year, "statement_quarter": quarter,
                "market_cap": current["market_cap"],
                "rank_eligible": bool(market.at[ticker, "close"] > 0 and market.at[ticker, "volume"] > 0),
            }
            row.update(factors); rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("펀더멘털 Factor 패널이 비었습니다.")
    frame.loc[~frame["rank_eligible"], list(FACTOR_IDS)] = np.nan
    transformed = cross_sectional_transform(frame, group_column=None)
    transformed = transformed.sort_values(["date", "ticker"]).reset_index(drop=True)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "fundamental_factor_panel.csv.gz"
    transformed.to_csv(target, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")
    coverage = {factor: float(transformed[factor].notna().mean()) for factor in FACTOR_IDS}
    result = {
        "schema_version": "kospi200-fundamental-factor-panel-v1",
        "status": "PASS_FACTOR_PANEL_MODEL_NOT_STARTED",
        "canonical_sha256": sha256(canonical_path), "identity_sha256": sha256(identity_path),
        "factor_contract_sha256": sha256(factor_contract),
        "membership_input_tree_sha256": tree_hash(membership_paths, membership_root),
        "market_input_tree_sha256": tree_hash(loaded_market_paths, market_root),
        "rows": len(transformed), "tickers": int(transformed["ticker"].nunique()),
        "min_date": pd.Timestamp(transformed["date"].min()).date().isoformat(),
        "max_date": pd.Timestamp(transformed["date"].max()).date().isoformat(),
        "membership_files_considered": len(membership_paths), "market_files_loaded": market_files_loaded,
        "minimum_year": minimum_year,
        "factor_coverage": coverage, "output_sha256": sha256(target),
        "protected_oos_accessed": False, "raw_modified": False, "model_started": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 일별 펀더멘털 Factor 패널")
    parser.add_argument("--canonical", type=Path, default=Path("data/processed/v2_kospi200_canonical_fundamentals/canonical_financial_accounts.csv"))
    parser.add_argument("--identity", type=Path, default=Path("data/processed/v2_kospi200_identity_frozen/identity_spells.csv"))
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--market-root", type=Path, default=Path("data/incoming/v25_kospi_raw/raw/market_stk"))
    parser.add_argument("--factor-contract", type=Path, default=Path("configs/fundamental_factor_contract_v1.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_fundamental_factor_panel"))
    parser.add_argument("--minimum-year", type=int, default=2015)
    args = parser.parse_args(argv)
    result = build(args.canonical, args.identity, args.membership_root, args.market_root, args.factor_contract, args.output_root, args.minimum_year)
    print(json.dumps({key: result[key] for key in ("status", "rows", "tickers", "min_date", "max_date", "output_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
