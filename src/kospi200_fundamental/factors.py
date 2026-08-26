"""확정 재무제표와 동시점 시가총액으로 계산하는 20개 펀더멘탈 Factor."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd


FACTOR_IDS = (
    "roe", "roa", "operating_margin", "net_margin", "cfo_to_assets",
    "earnings_yield", "book_to_market", "sales_to_market_cap", "cfo_yield", "free_cash_flow_yield",
    "debt_to_equity", "liabilities_to_assets", "current_ratio", "cash_to_assets", "equity_ratio",
    "revenue_growth_yoy", "operating_income_growth_yoy", "net_income_growth_yoy", "assets_growth_yoy", "equity_growth_yoy",
)


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float:
    try:
        n, d = float(numerator), float(denominator)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(n) or not np.isfinite(d) or d == 0:
        return float("nan")
    return n / d


def _growth(current: Mapping[str, float], prior: Mapping[str, float], key: str) -> float:
    previous = prior.get(key)
    value = current.get(key)
    ratio = _ratio(value, previous)
    return ratio - 1.0 if np.isfinite(ratio) else float("nan")


def compute_factors(current: Mapping[str, float], prior_year: Mapping[str, float]) -> dict[str, float]:
    """한 공시시점의 trailing/current canonical accounts로 20개 값을 계산한다."""
    assets = current.get("assets")
    equity = current.get("equity")
    revenue = current.get("revenue")
    market_cap = current.get("market_cap")
    cfo = current.get("operating_cash_flow")
    capex = current.get("capital_expenditure")
    return {
        "roe": _ratio(current.get("net_income"), equity),
        "roa": _ratio(current.get("net_income"), assets),
        "operating_margin": _ratio(current.get("operating_income"), revenue),
        "net_margin": _ratio(current.get("net_income"), revenue),
        "cfo_to_assets": _ratio(cfo, assets),
        "earnings_yield": _ratio(current.get("net_income"), market_cap),
        "book_to_market": _ratio(equity, market_cap),
        "sales_to_market_cap": _ratio(revenue, market_cap),
        "cfo_yield": _ratio(cfo, market_cap),
        "free_cash_flow_yield": _ratio(None if cfo is None or capex is None else float(cfo) - abs(float(capex)), market_cap),
        "debt_to_equity": _ratio(current.get("liabilities"), equity),
        "liabilities_to_assets": _ratio(current.get("liabilities"), assets),
        "current_ratio": _ratio(current.get("current_assets"), current.get("current_liabilities")),
        "cash_to_assets": _ratio(current.get("cash_and_equivalents"), assets),
        "equity_ratio": _ratio(equity, assets),
        "revenue_growth_yoy": _growth(current, prior_year, "revenue"),
        "operating_income_growth_yoy": _growth(current, prior_year, "operating_income"),
        "net_income_growth_yoy": _growth(current, prior_year, "net_income"),
        "assets_growth_yoy": _growth(current, prior_year, "assets"),
        "equity_growth_yoy": _growth(current, prior_year, "equity"),
    }


def cross_sectional_transform(frame: pd.DataFrame, *, group_column: str | None = "sector") -> pd.DataFrame:
    """날짜별 또는 날짜·섹터별 percentile와 robust z-score를 계산한다.

    원값 보간은 하지 않는다. 섹터 표본이 5개 미만이면 그 날짜의 전체 KOSPI 200
    단면으로 fallback하며, 이 선택은 각 날짜 안에서만 이루어진다.
    """
    required = {"date", "ticker", *FACTOR_IDS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"펀더멘탈 단면 필수 열 누락: {missing}")
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"], errors="raise").dt.normalize()
    use_sector = group_column is not None and group_column in output.columns
    for factor in FACTOR_IDS:
        values = pd.to_numeric(output[factor], errors="coerce")
        date_group = output["date"]
        percentile = values.groupby(date_group).rank(pct=True, method="average")
        median = values.groupby(date_group).transform("median")
        mad = (values - median).abs().groupby(date_group).transform("median")
        zscore = (values - median) / (1.4826 * mad.replace(0, np.nan))
        if use_sector:
            sector_keys = [output["date"], output[group_column].fillna("UNCLASSIFIED")]
            count = values.groupby(sector_keys).transform("count")
            sector_pct = values.groupby(sector_keys).rank(pct=True, method="average")
            sector_median = values.groupby(sector_keys).transform("median")
            sector_mad = (values - sector_median).abs().groupby(sector_keys).transform("median")
            sector_z = (values - sector_median) / (1.4826 * sector_mad.replace(0, np.nan))
            percentile = sector_pct.where(count >= 5, percentile)
            zscore = sector_z.where(count >= 5, zscore)
        output[f"{factor}__percentile"] = percentile
        output[f"{factor}__robust_z"] = zscore.clip(-5, 5)
    return output
