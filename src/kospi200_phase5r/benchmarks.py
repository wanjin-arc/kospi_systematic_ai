"""Phase 5R benchmark 분해와 방어 지표의 순수 함수."""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd

from .portfolio import EXCLUDED_SECURITY_IDS, EXCLUDED_TICKERS, normalize_ticker


class BenchmarkContractError(ValueError):
    """benchmark 입력 또는 정렬 계약 위반."""


def _dates(frame: pd.DataFrame, column: str = "date") -> pd.Series:
    if column not in frame.columns:
        raise BenchmarkContractError(f"필수 열 누락: {column}")
    values = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    if values.isna().any():
        raise BenchmarkContractError("benchmark date 파싱 실패")
    return values


def _returns(frame: pd.DataFrame, column: str = "daily_return") -> pd.Series:
    if column not in frame.columns:
        raise BenchmarkContractError(f"필수 열 누락: {column}")
    values = pd.to_numeric(frame[column], errors="coerce")
    if not values.map(math.isfinite).all() or values.le(-1).any():
        raise BenchmarkContractError("수익률은 유한하고 -100%보다 커야 합니다.")
    return values.astype(float)


def official_index_returns(index: pd.DataFrame) -> pd.DataFrame:
    """공식 KRX1028 종가를 일별 수익률과 기준 1의 level로 변환한다."""

    if "close" not in index.columns:
        raise BenchmarkContractError("공식 지수 close 열이 없습니다.")
    output = pd.DataFrame({"date": _dates(index), "close": pd.to_numeric(index["close"], errors="coerce")})
    if output["date"].duplicated().any():
        raise BenchmarkContractError("공식 지수 날짜가 중복됩니다.")
    if not (output["close"].map(math.isfinite) & output["close"].gt(0)).all():
        raise BenchmarkContractError("공식 지수 종가는 양의 유한값이어야 합니다.")
    output = output.sort_values("date", kind="mergesort").reset_index(drop=True)
    output["daily_return"] = output["close"].pct_change(fill_method=None).fillna(0.0)
    output["index_level"] = (1.0 + output["daily_return"]).cumprod()
    output["benchmark"] = "KRX1028_FULL"
    output["date"] = output["date"].dt.date.astype(str)
    return output[["date", "daily_return", "index_level", "benchmark"]]


def _is_excluded_row(frame: pd.DataFrame) -> pd.Series:
    tickers = frame["ticker"].map(normalize_ticker)
    mask = tickers.isin(EXCLUDED_TICKERS)
    if "security_id" in frame.columns:
        mask |= frame["security_id"].fillna("").astype(str).isin(EXCLUDED_SECURITY_IDS)
    return mask


def ex2_cap_proxy(
    market: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    base_level: float = 1.0,
) -> pd.DataFrame:
    """전일 PIT cap으로 두 대형주 제외 진단 proxy를 계산한다.

    수익률은 전일 membership과 전일 market cap으로 가중한다. 다만 권위 있는
    기업행위 조건표 없이 관측 listed_shares로 보유자 수량배율을 추론하지 않는다.
    20% 이상 변화가 하나라도 있으면 canonical proxy는 fail-closed 한다.
    이는 공식 유동주식 KOSPI200 지수가 아니다.
    """

    market_required = {"date", "ticker", "close", "market_cap"}
    member_required = {"date", "ticker"}
    if not market_required.issubset(market.columns):
        raise BenchmarkContractError(f"market 필수 열 누락: {sorted(market_required - set(market.columns))}")
    if not member_required.issubset(membership.columns):
        raise BenchmarkContractError(f"membership 필수 열 누락: {sorted(member_required - set(membership.columns))}")

    prices = market.copy()
    prices["_date"] = _dates(prices)
    prices["ticker"] = prices["ticker"].map(normalize_ticker)
    prices = prices.loc[~_is_excluded_row(prices)].copy()
    if prices.duplicated(["_date", "ticker"]).any():
        raise BenchmarkContractError("market date/ticker가 중복됩니다.")
    for column in ("close", "market_cap"):
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
        if not (prices[column].map(math.isfinite) & prices[column].gt(0)).all():
            raise BenchmarkContractError(f"{column}은 양의 유한값이어야 합니다.")
    if "listed_shares" in prices.columns:
        prices["listed_shares"] = pd.to_numeric(prices["listed_shares"], errors="coerce")
        if not (prices["listed_shares"].map(math.isfinite) & prices["listed_shares"].gt(0)).all():
            raise BenchmarkContractError("listed_shares는 양의 유한값이어야 합니다.")

    members = membership.copy()
    members["_date"] = _dates(members)
    members["ticker"] = members["ticker"].map(normalize_ticker)
    members = members.loc[~_is_excluded_row(members)].copy()
    if members.duplicated(["_date", "ticker"]).any():
        raise BenchmarkContractError("membership date/ticker가 중복됩니다.")

    sessions = sorted(members["_date"].drop_duplicates())
    if not sessions:
        raise BenchmarkContractError("membership 세션이 없습니다.")
    indexed = prices.set_index(["_date", "ticker"])
    member_map = {
        session: sorted(group["ticker"].tolist())
        for session, group in members.groupby("_date", sort=True)
    }

    rows = [{
        "date": sessions[0].date().isoformat(),
        "daily_return": 0.0,
        "index_level": float(base_level),
        "constituent_count": len(member_map[sessions[0]]),
        "benchmark": "EX2_CAP",
    }]
    level = float(base_level)
    for previous, current in zip(sessions, sessions[1:]):
        weighted_returns: list[float] = []
        weights: list[float] = []
        for ticker in member_map[previous]:
            previous_key = (previous, ticker)
            current_key = (current, ticker)
            if previous_key not in indexed.index or current_key not in indexed.index:
                raise BenchmarkContractError(f"EX2_CAP 가격 누락: {previous.date()}->{current.date()} {ticker}")
            prior = indexed.loc[previous_key]
            now = indexed.loc[current_key]
            price_ratio = float(now["close"] / prior["close"])
            if "listed_shares" in prices.columns:
                share_ratio = float(now["listed_shares"] / prior["listed_shares"])
                if abs(math.log(share_ratio)) >= math.log(1.20):
                    raise BenchmarkContractError(
                        f"미해결 share reset은 canonical EX2에서 추론할 수 없습니다: "
                        f"{current.date()} {ticker}"
                    )
            weighted_returns.append(price_ratio - 1.0)
            weights.append(float(prior["market_cap"]))
        if not weights or sum(weights) <= 0:
            raise BenchmarkContractError(f"EX2_CAP 유효 구성종목 없음: {previous.date()}")
        daily_return = float(np.average(weighted_returns, weights=weights))
        level *= 1.0 + daily_return
        rows.append({
            "date": current.date().isoformat(),
            "daily_return": daily_return,
            "index_level": level,
            "constituent_count": len(weights),
            "benchmark": "EX2_CAP",
        })
    return pd.DataFrame(rows)


def ex2_share_reset_sensitivities(
    market: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    base_level: float = 1.0,
    share_reset_threshold: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """미해결 주식수 변동을 두 비수익률 민감도로 보존하고 누락 없이 감사한다.

    효력일·보유자 수량배율·현금/권리 조건이 완비된 resolved action table이
    없으므로 어느 변동도 canonical EX2 수익률로 추정하지 않는다. 종목을
    제거하거나 당일 가중치를 재정규화하지 않고, 고정 단위가격과 발행자
    시가총액 가치의 두 극단적 민감도만 병렬 산출한다.
    """

    market_required = {"date", "ticker", "close", "market_cap", "listed_shares"}
    member_required = {"date", "ticker"}
    if not market_required.issubset(market.columns):
        raise BenchmarkContractError(
            f"market 필수 열 누락: {sorted(market_required - set(market.columns))}"
        )
    if not member_required.issubset(membership.columns):
        raise BenchmarkContractError(
            f"membership 필수 열 누락: {sorted(member_required - set(membership.columns))}"
        )
    if not 0.0 < float(share_reset_threshold) < 1.0:
        raise BenchmarkContractError("share reset threshold는 (0, 1) 범위여야 합니다.")

    prices = market.copy()
    prices["_date"] = _dates(prices)
    prices["ticker"] = prices["ticker"].map(normalize_ticker)
    prices = prices.loc[~_is_excluded_row(prices)].copy()
    if prices.duplicated(["_date", "ticker"]).any():
        raise BenchmarkContractError("market date/ticker가 중복됩니다.")
    for column in ("close", "market_cap", "listed_shares"):
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
        if not (prices[column].map(math.isfinite) & prices[column].gt(0)).all():
            raise BenchmarkContractError(f"{column}은 양의 유한값이어야 합니다.")

    members = membership.copy()
    members["_date"] = _dates(members)
    members["ticker"] = members["ticker"].map(normalize_ticker)
    members = members.loc[~_is_excluded_row(members)].copy()
    if members.duplicated(["_date", "ticker"]).any():
        raise BenchmarkContractError("membership date/ticker가 중복됩니다.")
    sessions = sorted(members["_date"].drop_duplicates())
    if not sessions:
        raise BenchmarkContractError("membership 세션이 없습니다.")
    indexed = prices.set_index(["_date", "ticker"])
    member_map = {
        session: sorted(group["ticker"].tolist())
        for session, group in members.groupby("_date", sort=True)
    }

    common_first = {
        "date": sessions[0].date().isoformat(),
        "daily_return": 0.0,
        "index_level": float(base_level),
        "constituent_count": len(member_map[sessions[0]]),
        "ambiguous_share_reset_count": 0,
        "ambiguous_share_reset_prior_weight": 0.0,
    }
    price_rows = [{**common_first, "benchmark": "EX2_PRICE_UNIT_SENSITIVITY"}]
    issuer_rows = [{**common_first, "benchmark": "EX2_ISSUER_CAP_VALUE_SENSITIVITY"}]
    price_level = float(base_level)
    issuer_level = float(base_level)
    event_ledger: list[dict[str, object]] = []

    for previous, current in zip(sessions, sessions[1:]):
        tickers = member_map[previous]
        prior_caps: dict[str, float] = {}
        for ticker in tickers:
            previous_key = (previous, ticker)
            current_key = (current, ticker)
            if previous_key not in indexed.index or current_key not in indexed.index:
                raise BenchmarkContractError(
                    f"EX2 sensitivity 가격 누락: {previous.date()}->{current.date()} {ticker}"
                )
            prior_caps[ticker] = float(indexed.loc[previous_key]["market_cap"])
        total_prior_cap = float(sum(prior_caps.values()))
        if not prior_caps or total_prior_cap <= 0:
            raise BenchmarkContractError(f"EX2 sensitivity 유효 구성종목 없음: {previous.date()}")

        price_ratios: list[float] = []
        issuer_ratios: list[float] = []
        weights: list[float] = []
        day_events = 0
        day_event_weight = 0.0
        for ticker in tickers:
            prior = indexed.loc[(previous, ticker)]
            now = indexed.loc[(current, ticker)]
            price_ratio = float(now["close"] / prior["close"])
            issuer_ratio = float(now["market_cap"] / prior["market_cap"])
            share_ratio = float(now["listed_shares"] / prior["listed_shares"])
            if not all(
                math.isfinite(value) and value > 0
                for value in (price_ratio, issuer_ratio, share_ratio)
            ):
                raise BenchmarkContractError(
                    f"EX2 sensitivity 비율 오류: {current.date()} {ticker}"
                )
            is_reset = abs(math.log(share_ratio)) >= math.log(1.0 + share_reset_threshold)
            if is_reset:
                prior_weight = prior_caps[ticker] / total_prior_cap
                day_events += 1
                day_event_weight += prior_weight
                event_ledger.append(
                    {
                        "previous_date": previous.date().isoformat(),
                        "effective_date": current.date().isoformat(),
                        "ticker": ticker,
                        "prior_weight": prior_weight,
                        "share_ratio": share_ratio,
                        "price_ratio": price_ratio,
                        "issuer_cap_value_ratio": issuer_ratio,
                        "observed_mechanical_reset": bool(now.get("mechanical_reset", False)),
                        "resolved_terms_available": False,
                    }
                )
            price_ratios.append(price_ratio)
            issuer_ratios.append(issuer_ratio if is_reset else price_ratio)
            weights.append(prior_caps[ticker])

        price_return = float(np.average(np.asarray(price_ratios) - 1.0, weights=weights))
        issuer_return = float(np.average(np.asarray(issuer_ratios) - 1.0, weights=weights))
        price_level *= 1.0 + price_return
        issuer_level *= 1.0 + issuer_return
        common = {
            "date": current.date().isoformat(),
            "constituent_count": len(weights),
            "ambiguous_share_reset_count": day_events,
            "ambiguous_share_reset_prior_weight": day_event_weight,
        }
        price_rows.append(
            {
                **common,
                "daily_return": price_return,
                "index_level": price_level,
                "benchmark": "EX2_PRICE_UNIT_SENSITIVITY",
            }
        )
        issuer_rows.append(
            {
                **common,
                "daily_return": issuer_return,
                "index_level": issuer_level,
                "benchmark": "EX2_ISSUER_CAP_VALUE_SENSITIVITY",
            }
        )

    audit: dict[str, object] = {
        "schema_version": "ex2-share-reset-sensitivity-v1",
        "share_reset_threshold": float(share_reset_threshold),
        "ambiguous_event_count": len(event_ledger),
        "ambiguous_event_dates": len({row["effective_date"] for row in event_ledger}),
        "maximum_daily_ambiguous_prior_weight": max(
            (float(row["ambiguous_share_reset_prior_weight"]) for row in price_rows),
            default=0.0,
        ),
        "resolved_action_contract_complete": len(event_ledger) == 0,
        "stable_identity_contract_complete": False,
        "identity_contract": "TICKER_DERIVED_NOT_HISTORICALLY_RESOLVED",
        "canonical_ex2_return_evaluable": False,
        "price_unit_sensitivity_self_financing": False,
        "issuer_cap_value_sensitivity_self_financing": False,
        "sensitivities_are_return_bounds": False,
        "event_ledger": event_ledger,
    }
    return pd.DataFrame(price_rows), pd.DataFrame(issuer_rows), audit


def exposure_matched_krx1028(
    official_returns: pd.DataFrame,
    exposures: pd.DataFrame,
    *,
    cash_daily_return: float = 0.0,
) -> pd.DataFrame:
    """전략의 당일 유효 주식노출만큼 공식지수를 보유한 비교선을 만든다."""

    official = pd.DataFrame({"date": _dates(official_returns), "index_return": _returns(official_returns)})
    if official["date"].duplicated().any():
        raise BenchmarkContractError("공식지수 return 날짜가 중복됩니다.")
    if not {"date", "stock_exposure"}.issubset(exposures.columns):
        raise BenchmarkContractError("exposures 필수 열 누락")
    exposure = pd.DataFrame({
        "date": _dates(exposures),
        "stock_exposure": pd.to_numeric(exposures["stock_exposure"], errors="coerce"),
    })
    if exposure["date"].duplicated().any():
        raise BenchmarkContractError("주식노출 날짜가 중복됩니다.")
    if not exposure["stock_exposure"].map(math.isfinite).all() or not exposure["stock_exposure"].between(0, 1).all():
        raise BenchmarkContractError("stock_exposure는 [0, 1] 범위여야 합니다.")
    if not math.isfinite(cash_daily_return) or cash_daily_return <= -1:
        raise BenchmarkContractError("cash_daily_return이 유효하지 않습니다.")
    output = official.merge(exposure, on="date", how="left", validate="one_to_one")
    if output["stock_exposure"].isna().any():
        raise BenchmarkContractError("공식지수 날짜의 주식노출이 누락됐습니다.")
    output["daily_return"] = (
        output["stock_exposure"] * output["index_return"]
        + (1.0 - output["stock_exposure"]) * cash_daily_return
    )
    output["index_level"] = (1.0 + output["daily_return"]).cumprod()
    output["benchmark"] = "EXPOSURE_MATCHED_KRX1028"
    output["date"] = output["date"].dt.date.astype(str)
    return output[["date", "daily_return", "index_level", "stock_exposure", "benchmark"]]


def compounded_return(values: pd.Series) -> float:
    returns = pd.to_numeric(values, errors="coerce")
    if returns.isna().any() or not returns.map(math.isfinite).all() or returns.le(-1).any():
        raise BenchmarkContractError("복리 수익률 입력이 유효하지 않습니다.")
    return float((1.0 + returns).prod() - 1.0)


def max_drawdown(values: pd.Series) -> float:
    returns = pd.to_numeric(values, errors="coerce")
    if returns.empty:
        raise BenchmarkContractError("MDD 입력이 비어 있습니다.")
    wealth = (1.0 + returns).cumprod()
    return float((wealth / wealth.cummax() - 1.0).min())


def _aligned_returns(
    strategy: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> pd.DataFrame:
    left = pd.DataFrame({"date": _dates(strategy), "strategy": _returns(strategy)})
    right = pd.DataFrame({"date": _dates(benchmark), "benchmark": _returns(benchmark)})
    if left["date"].duplicated().any() or right["date"].duplicated().any():
        raise BenchmarkContractError("수익률 날짜가 중복됩니다.")
    output = left.merge(right, on="date", how="inner", validate="one_to_one").sort_values("date")
    if len(output) != len(left) or len(output) != len(right):
        raise BenchmarkContractError("전략과 benchmark 날짜가 정확히 일치하지 않습니다.")
    return output.reset_index(drop=True)


def rolling_active_returns(
    strategy: pd.DataFrame,
    benchmark: pd.DataFrame,
    *,
    window: int = 252,
) -> pd.DataFrame:
    """각 full window의 복리 전략수익률 minus benchmark 수익률을 계산한다."""

    if window <= 1:
        raise BenchmarkContractError("rolling window는 2 이상이어야 합니다.")
    aligned = _aligned_returns(strategy, benchmark)
    if len(aligned) < window:
        return pd.DataFrame(columns=["date", "strategy_return", "benchmark_return", "active_return"])
    strategy_roll = (1.0 + aligned["strategy"]).rolling(window).apply(np.prod, raw=True) - 1.0
    benchmark_roll = (1.0 + aligned["benchmark"]).rolling(window).apply(np.prod, raw=True) - 1.0
    output = pd.DataFrame({
        "date": aligned["date"],
        "strategy_return": strategy_roll,
        "benchmark_return": benchmark_roll,
        "active_return": strategy_roll - benchmark_roll,
    }).dropna().reset_index(drop=True)
    output["date"] = output["date"].dt.date.astype(str)
    return output


def calendar_year_active_returns(strategy: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    aligned = _aligned_returns(strategy, benchmark)
    aligned["year"] = aligned["date"].dt.year
    rows = []
    for year, group in aligned.groupby("year", sort=True):
        strategy_return = compounded_return(group["strategy"])
        benchmark_return = compounded_return(group["benchmark"])
        rows.append({
            "year": int(year),
            "strategy_return": strategy_return,
            "benchmark_return": benchmark_return,
            "active_return": strategy_return - benchmark_return,
        })
    return pd.DataFrame(rows)


def downside_capture(strategy: pd.DataFrame, benchmark: pd.DataFrame) -> float:
    """benchmark 하락일 복리수익률 대비 전략 복리수익률의 비율."""

    aligned = _aligned_returns(strategy, benchmark)
    down = aligned.loc[aligned["benchmark"].lt(0)]
    if down.empty:
        raise BenchmarkContractError("downside capture를 계산할 benchmark 하락일이 없습니다.")
    benchmark_down = compounded_return(down["benchmark"])
    if benchmark_down >= 0:
        raise BenchmarkContractError("benchmark 하락일 복리수익률이 음수가 아닙니다.")
    return compounded_return(down["strategy"]) / benchmark_down


def comparison_metrics(
    strategy: pd.DataFrame,
    benchmark: pd.DataFrame,
    *,
    rolling_window: int = 252,
) -> dict[str, float]:
    """gate에 필요한 전체·calendar·rolling·downside 지표를 반환한다."""

    aligned = _aligned_returns(strategy, benchmark)
    rolling = rolling_active_returns(strategy, benchmark, window=rolling_window)
    calendar = calendar_year_active_returns(strategy, benchmark)
    return {
        "strategy_total_return": compounded_return(aligned["strategy"]),
        "benchmark_total_return": compounded_return(aligned["benchmark"]),
        "active_total_return": compounded_return(aligned["strategy"])
        - compounded_return(aligned["benchmark"]),
        "strategy_mdd": max_drawdown(aligned["strategy"]),
        "benchmark_mdd": max_drawdown(aligned["benchmark"]),
        "worst_rolling_active_return": float(rolling["active_return"].min()) if not rolling.empty else math.nan,
        "worst_calendar_active_return": float(calendar["active_return"].min()),
        "downside_capture": downside_capture(strategy, benchmark),
    }


def benchmark_decomposition(
    phase5r: pd.DataFrame,
    neutral_core: pd.DataFrame,
    ex2_cap: pd.DataFrame,
    krx1028_full: pd.DataFrame,
) -> Mapping[str, float]:
    """명세의 네 가지 성과 차이를 복리 총수익률 차이로 분해한다."""

    frames = [phase5r, neutral_core, ex2_cap, krx1028_full]
    normalized = []
    for frame in frames:
        normalized.append(pd.DataFrame({"date": _dates(frame), "daily_return": _returns(frame)}))
    reference_dates = normalized[0]["date"].tolist()
    if any(frame["date"].tolist() != reference_dates for frame in normalized[1:]):
        raise BenchmarkContractError("benchmark decomposition 날짜와 순서가 일치하지 않습니다.")
    totals = [compounded_return(frame["daily_return"]) for frame in normalized]
    return {
        "phase5r_minus_neutral_core": totals[0] - totals[1],
        "ex2_cap_minus_krx1028_full": totals[2] - totals[3],
        "neutral_core_minus_ex2_cap": totals[1] - totals[2],
        "phase5r_minus_krx1028_full": totals[0] - totals[3],
    }
