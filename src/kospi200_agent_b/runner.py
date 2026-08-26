"""PIT 펀더멘털로 일별 KOSPI 200 Top 30을 만드는 Agent B 실행기."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kospi200_fundamental import FACTOR_IDS


FORBIDDEN_PARTS = {"sealed", "final_oos_v24"}
NEGATIVE_FACTORS = {"debt_to_equity", "liabilities_to_assets", "dilution_252"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_path(path: Path) -> None:
    if FORBIDDEN_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def _market_columns(frame: pd.DataFrame) -> tuple[str, str, str, str]:
    ticker = next(column for column in ("종목코드", "ISU_SRT_CD") if column in frame.columns)
    open_ = next(column for column in ("시가", "TDD_OPNPRC") if column in frame.columns)
    close = next(column for column in ("종가", "TDD_CLSPRC") if column in frame.columns)
    shares = next(column for column in ("상장주식수", "LIST_SHRS") if column in frame.columns)
    return ticker, open_, close, shares


def load_market(market_root: Path, start_year: int, end_year: int) -> tuple[pd.DataFrame, list[str], list[Path]]:
    guard_path(market_root)
    paths = sorted(
        path for year in range(start_year, end_year + 1)
        for path in (market_root / str(year)).glob("*.csv.gz")
    )
    if not paths:
        raise FileNotFoundError("허용 기간 KRX market_stk 파일이 없습니다.")
    pieces: list[pd.DataFrame] = []
    sessions: list[str] = []
    for path in paths:
        day = path.stem.split(".")[0]
        date = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        frame = pd.read_csv(path, compression="gzip", encoding="cp949", dtype=str, keep_default_na=False)
        ticker, open_, close, shares = _market_columns(frame)
        part = frame[[ticker, open_, close, shares]].copy()
        part.columns = ["ticker", "open", "close", "listed_shares"]
        part["date"] = date
        part["ticker"] = part["ticker"].str.replace(r"\D", "", regex=True).str.zfill(6)
        for column in ("open", "close", "listed_shares"):
            part[column] = pd.to_numeric(part[column].str.replace(",", "", regex=False), errors="coerce")
        pieces.append(part)
        sessions.append(date)
    market = pd.concat(pieces, ignore_index=True).drop_duplicates(["date", "ticker"])
    return market, sessions, paths


def compute_dilution(market: pd.DataFrame, lookback: int = 252) -> pd.DataFrame:
    """가격 역조정과 상쇄되는 큰 주식수 변화는 기계적 reset으로 제외한다."""
    frame = market.sort_values(["ticker", "date"]).copy()
    groups = frame.groupby("ticker", sort=False)
    share_ratio = frame["listed_shares"] / groups["listed_shares"].shift(1)
    price_ratio = frame["close"] / groups["close"].shift(1)
    valid = (share_ratio > 0) & (price_ratio > 0)
    large = valid & (np.abs(np.log(share_ratio)) >= math.log(1.20))
    mechanical = large & (np.abs(np.log(share_ratio) + np.log(price_ratio)) <= math.log(1.15))
    contribution = np.log(share_ratio.where(valid)).where(~mechanical, 0.0)
    frame["mechanical_share_reset"] = mechanical.fillna(False)
    frame["dilution_252"] = (
        contribution.groupby(frame["ticker"], sort=False)
        .rolling(lookback, min_periods=max(20, lookback // 2)).sum()
        .reset_index(level=0, drop=True).pipe(np.exp).sub(1.0)
    )
    return frame[["date", "ticker", "open", "listed_shares", "dilution_252", "mechanical_share_reset"]]


def attach_forward_rank(frame: pd.DataFrame, market: pd.DataFrame, sessions: list[str], horizon: int) -> pd.DataFrame:
    index = {date: i for i, date in enumerate(sessions)}
    boundaries = {
        date: (sessions[i + 1], sessions[i + horizon + 1])
        for date, i in index.items() if i + horizon + 1 < len(sessions)
    }
    opens = market.set_index(["date", "ticker"])["open"]
    output = frame.copy()
    entries: list[float] = []
    exits: list[float] = []
    for row in output[["date", "ticker"]].itertuples(index=False):
        boundary = boundaries.get(str(row.date))
        if boundary is None:
            entries.append(np.nan); exits.append(np.nan); continue
        entries.append(opens.get((boundary[0], str(row.ticker)), np.nan))
        exits.append(opens.get((boundary[1], str(row.ticker)), np.nan))
    output["forward_return_63"] = np.asarray(exits) / np.asarray(entries) - 1.0
    output.loc[(np.asarray(entries) <= 0) | (np.asarray(exits) <= 0), "forward_return_63"] = np.nan
    output["target_rank"] = output.groupby("date")["forward_return_63"].rank(pct=True, method="average")
    return output


def eligible_daily_panel(panel: pd.DataFrame, dilution: pd.DataFrame, top_market_cap: int) -> pd.DataFrame:
    output = panel.merge(dilution, on=["date", "ticker"], how="left", validate="one_to_one")
    output["market_cap_rank"] = output.groupby("date")["market_cap"].rank(method="first", ascending=False)
    output = output[(output["rank_eligible"] == True) & (output["market_cap_rank"] <= top_market_cap)].copy()  # noqa: E712
    output["dilution_252__percentile"] = output.groupby("date")["dilution_252"].rank(pct=True, method="average")
    return output


def month_end_rows(frame: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(frame["date"])
    chosen = frame.assign(_date=dates).groupby(dates.dt.to_period("M"))["_date"].max()
    return frame[dates.isin(chosen.to_numpy())].copy()


def feature_columns() -> list[str]:
    return [f"{factor}__percentile" for factor in FACTOR_IDS] + ["dilution_252__percentile"]


def equal_score(frame: pd.DataFrame) -> np.ndarray:
    values = frame[feature_columns()].fillna(0.5).to_numpy(float)
    signs = np.asarray([-1.0 if name.removesuffix("__percentile") in NEGATIVE_FACTORS else 1.0 for name in feature_columns()])
    return np.nanmean(values * signs, axis=1)


def make_model(name: str, seed: int):
    if name == "ridge_a10":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", Ridge(alpha=10.0))])
    if name == "hist_gbdt_d3":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", HistGradientBoostingRegressor(
            learning_rate=0.05, max_depth=3, max_iter=100, l2_regularization=1.0, random_state=seed,
        ))])
    raise ValueError(name)


def _spearman(frame: pd.DataFrame) -> float:
    values = [group["score"].corr(group["target_rank"], method="spearman") for _, group in frame.groupby("date")]
    values = [value for value in values if pd.notna(value)]
    return float(np.mean(values)) if values else float("nan")


def _ndcg30(frame: pd.DataFrame) -> float:
    results = []
    for _, group in frame.groupby("date"):
        ranked = group.sort_values(["score", "ticker"], ascending=[False, True]).head(30)
        ideal = group.sort_values(["target_rank", "ticker"], ascending=[False, True]).head(30)
        discount = 1.0 / np.log2(np.arange(2, len(ranked) + 2))
        dcg = float(np.sum(ranked["target_rank"].to_numpy() * discount))
        idcg = float(np.sum(ideal["target_rank"].to_numpy() * discount))
        if idcg > 0:
            results.append(dcg / idcg)
    return float(np.mean(results)) if results else float("nan")


def _gzip_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    panel_path, market_root = Path(config["factor_panel"]), Path(config["market_root"])
    guard_path(panel_path); guard_path(market_root)
    panel = pd.read_csv(panel_path, dtype={"ticker": str})
    panel["ticker"] = panel["ticker"].str.zfill(6)
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    if panel.empty or panel["date"].max() > config["data_end"]:
        raise ValueError("허용 데이터 경계를 위반했습니다.")
    market, sessions, market_paths = load_market(market_root, int(config["data_start"][:4]), int(config["data_end"][:4]))
    dilution = compute_dilution(market, int(config["dilution_lookback_sessions"]))
    daily = eligible_daily_panel(panel, dilution, int(config["market_cap_universe_size"]))
    labeled = attach_forward_rank(month_end_rows(daily), market, sessions, int(config["target_horizon_sessions"]))
    labeled = labeled.dropna(subset=["target_rank"])
    candidates = list(config["models"])
    metrics: list[dict[str, object]] = []
    scored_parts: dict[str, list[pd.DataFrame]] = {name: [] for name in candidates}
    fold_cutoffs: dict[int, str] = {}
    session_index = {date: i for i, date in enumerate(sessions)}
    for validation_year in config["validation_years"]:
        validation = labeled[labeled["date"].str[:4].astype(int) == int(validation_year)].copy()
        if validation.empty:
            continue
        first = validation["date"].min()
        cutoff_i = session_index[first] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        if cutoff_i < 0:
            continue
        cutoff = sessions[cutoff_i]
        fold_cutoffs[int(validation_year)] = cutoff
        train = labeled[labeled["date"] <= cutoff].copy()
        train = train.dropna(subset=["target_rank"])
        if train["date"].nunique() < int(config["minimum_train_months"]):
            continue
        for name in candidates:
            if name == "equal_composite":
                score = equal_score(validation)
            else:
                model = make_model(name, int(config["seed"]))
                model.fit(train[feature_columns()], train["target_rank"])
                score = model.predict(validation[feature_columns()])
            part = validation[["date", "ticker", "target_rank"]].copy()
            part["score"] = score; part["model"] = name; part["validation_year"] = validation_year
            scored_parts[name].append(part)
            metrics.append({"model": name, "validation_year": validation_year, "train_cutoff": cutoff,
                            "train_rows": len(train), "validation_rows": len(validation),
                            "rank_ic": _spearman(part), "ndcg_at_30": _ndcg30(part)})
    metric_frame = pd.DataFrame(metrics)
    if metric_frame.empty:
        raise RuntimeError("유효한 walk-forward fold가 없습니다.")
    summary = metric_frame.groupby("model", as_index=False).agg(mean_rank_ic=("rank_ic", "mean"), mean_ndcg_at_30=("ndcg_at_30", "mean"), folds=("validation_year", "count"))
    simplicity = {"equal_composite": 0, "ridge_a10": 1, "hist_gbdt_d3": 2}
    summary["simplicity"] = summary["model"].map(simplicity)
    summary = summary.sort_values(["mean_rank_ic", "mean_ndcg_at_30", "simplicity"], ascending=[False, False, True])
    selected = str(summary.iloc[0]["model"])
    all_scored = pd.concat(scored_parts[selected], ignore_index=True)
    top_parts = []
    for year in sorted(all_scored["validation_year"].unique()):
        train_monthly = labeled[labeled["date"] <= fold_cutoffs[int(year)]].copy()
        year_daily = daily[daily["date"].str[:4].astype(int) == int(year)].copy()
        if selected == "equal_composite":
            year_daily["agent_b_score"] = equal_score(year_daily)
        else:
            model = make_model(selected, int(config["seed"]))
            model.fit(train_monthly[feature_columns()], train_monthly["target_rank"])
            year_daily["agent_b_score"] = model.predict(year_daily[feature_columns()])
        year_daily["agent_b_rank"] = year_daily.groupby("date")["agent_b_score"].rank(method="first", ascending=False)
        top_parts.append(year_daily[year_daily["agent_b_rank"] <= int(config["daily_selection_size"])])
    top = pd.concat(top_parts, ignore_index=True).sort_values(["date", "agent_b_rank", "ticker"])
    output_root.mkdir(parents=True, exist_ok=False)
    metric_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    summary.to_csv(output_root / "model_summary.csv", index=False, float_format="%.12g", lineterminator="\n")
    top_columns = ["date", "ticker", "membership_name", "market_cap", "market_cap_rank", "listed_shares", "dilution_252", "statement_year", "statement_quarter", "agent_b_score", "agent_b_rank"]
    _gzip_csv(top[top_columns], output_root / "daily_top30.csv.gz")
    if selected == "ridge_a10":
        final_model = make_model(selected, int(config["seed"]))
        final_model.fit(labeled[feature_columns()], labeled["target_rank"])
        model_state = {
            "model": selected, "features": feature_columns(),
            "imputer_statistics": final_model.named_steps["imputer"].statistics_.tolist(),
            "scaler_mean": final_model.named_steps["scale"].mean_.tolist(),
            "scaler_scale": final_model.named_steps["scale"].scale_.tolist(),
            "coefficient": final_model.named_steps["model"].coef_.tolist(),
            "intercept": float(final_model.named_steps["model"].intercept_),
            "fit_rows": len(labeled), "fit_max_signal_date": str(labeled["date"].max()),
        }
    elif selected == "equal_composite":
        model_state = {"model": selected, "features": feature_columns(),
                       "directions": [-1 if name.removesuffix("__percentile") in NEGATIVE_FACTORS else 1 for name in feature_columns()]}
    else:
        model_state = {"model": selected, "features": feature_columns(), "deterministic_refit_from_config_required": True}
    _json(output_root / "selected_model.json", model_state)
    daily_counts = top.groupby("date").size()
    data_audit = {
        "factor_panel_rows_loaded": len(panel), "factor_panel_min_date": str(panel["date"].min()),
        "factor_panel_max_date": str(panel["date"].max()),
        "minimum_statement_business_year": int(panel["statement_year"].min()),
        "independent_2014_filing_loaded": False, "comparison_values_backdated_to_2014": False,
        "market_files_loaded": len(market_paths), "market_min_date": min(sessions), "market_max_date": max(sessions),
        "mechanical_share_resets": int(dilution["mechanical_share_reset"].sum()),
        "dilution_coverage_eligible": float(daily["dilution_252"].notna().mean()),
        "top30_dates": int(daily_counts.size), "top30_min_count": int(daily_counts.min()),
        "top30_max_count": int(daily_counts.max()), "top30_duplicate_date_ticker": int(top.duplicated(["date", "ticker"]).sum()),
        "market_cap_rank_max_in_output": float(top["market_cap_rank"].max()),
        "legacy_v1_development_test_partition_accessed": False,
        "v2_consumed_development_2022_2023_loaded": bool(panel["date"].max() >= "2022-01-01"),
        "final_oos_accessed": False,
    }
    _json(output_root / "data_audit.json", data_audit)
    input_hashes = {"factor_panel": sha256(panel_path), "config": sha256(config_path)}
    market_digest = hashlib.sha256("\n".join(f"{p.relative_to(market_root).as_posix()}:{sha256(p)}" for p in market_paths).encode()).hexdigest()
    manifest = {
        "schema_version": "kospi200-agent-b-phase2-v1", "experiment_id": config["experiment_id"],
        "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "selected_model": selected,
        "data_min_date": str(panel["date"].min()), "data_max_date": str(panel["date"].max()),
        "loaded_market_files": len(market_paths), "market_input_tree_sha256": market_digest,
        "input_hashes": input_hashes, "monthly_label_rows": len(labeled), "daily_top30_rows": len(top),
        "top30_min_date": str(top["date"].min()), "top30_max_date": str(top["date"].max()),
        "legacy_v1_development_test_partition_accessed": False,
        "v2_consumed_development_2022_2023_loaded": bool(panel["date"].max() >= "2022-01-01"),
        "final_oos_accessed": False, "portfolio_backtest_run": False,
    }
    for name in ("fold_metrics.csv", "model_summary.csv", "daily_top30.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
