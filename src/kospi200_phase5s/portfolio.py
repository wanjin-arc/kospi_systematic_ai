"""Phase 5S의 동결된 비시가총액가중 포트폴리오 계약.

이 모듈의 주문 생성기는 신호일 종가만 입력받는다. 실제 ``t+1`` 시가나
거래량은 주문을 만들지 여부를 결정하는 입력이 아니며, precommitted buy
limit의 체결 여부는 백테스트 엔진이 실행일 bar로 판정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import math
import re

import pandas as pd

from kospi100_backtest.types import Order, Side


EXCLUDED_TICKERS = frozenset({"005930", "000660"})
EXCLUDED_SECURITY_IDS = frozenset({"KRX_COMMON:005930", "KRX_COMMON:000660"})


class PortfolioContractError(ValueError):
    """동결된 Phase 5S 포트폴리오 계약 위반."""


@dataclass(frozen=True)
class Phase5SPortfolioRules:
    lookback_sessions: int = 20
    core_size: int = 50
    alpha_size: int = 10
    core_weight: Decimal = Decimal("0.014")
    alpha_increment: Decimal = Decimal("0.020")
    neutral_weight: Decimal = Decimal("0.018")
    cash_weight: Decimal = Decimal("0.10")
    limit_multiplier: Decimal = Decimal("1.05")
    maximum_holding_sessions: int = 20

    def __post_init__(self) -> None:
        if self.lookback_sessions <= 0 or self.core_size <= 0:
            raise ValueError("lookback_sessions와 core_size는 양수여야 합니다.")
        if not 0 < self.alpha_size <= self.core_size:
            raise ValueError("alpha_size는 1 이상 core_size 이하여야 합니다.")
        invested = self.core_weight * self.core_size + self.alpha_increment * self.alpha_size
        neutral_invested = self.neutral_weight * self.core_size
        expected = Decimal("1") - self.cash_weight
        if invested != expected or neutral_invested != expected:
            raise ValueError("동결 비중은 주식노출과 현금 비중의 합이 정확히 1이어야 합니다.")
        if self.limit_multiplier != Decimal("1.05"):
            raise ValueError("Phase 5S buy-limit multiplier는 1.05로 동결됩니다.")
        if self.maximum_holding_sessions != 20:
            raise ValueError("Phase 5S 보유기간은 20세션으로 동결됩니다.")

    @property
    def stock_exposure(self) -> Decimal:
        return Decimal("1") - self.cash_weight


DEFAULT_RULES = Phase5SPortfolioRules()


def normalize_ticker(value: object) -> str:
    """KRX 단축코드를 결정적인 6자리 문자열로 정규화한다."""

    if value is None or pd.isna(value):
        raise PortfolioContractError("ticker가 비어 있습니다.")
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if not digits or len(digits) > 6:
        raise PortfolioContractError(f"유효하지 않은 6자리 ticker: {value!r}")
    return digits.zfill(6)


def _normalized_tickers(frame: pd.DataFrame, column: str = "ticker") -> pd.Series:
    if column not in frame.columns:
        raise PortfolioContractError(f"필수 열 누락: {column}")
    return frame[column].map(normalize_ticker)


def excluded_mask(
    frame: pd.DataFrame,
    *,
    ticker_column: str = "ticker",
    security_id_column: str = "security_id",
) -> pd.Series:
    """ticker와 stable security ID 중 하나라도 일치하면 제외한다."""

    tickers = _normalized_tickers(frame, ticker_column)
    by_ticker = tickers.isin(EXCLUDED_TICKERS)
    if security_id_column not in frame.columns:
        return by_ticker
    security_ids = frame[security_id_column].fillna("").astype(str).str.strip()
    return by_ticker | security_ids.isin(EXCLUDED_SECURITY_IDS)


def filter_excluded_securities(frame: pd.DataFrame) -> pd.DataFrame:
    """두 대형주를 이중 계약으로 제거하고 ticker를 정규화한다."""

    output = frame.copy()
    output["ticker"] = _normalized_tickers(output)
    return output.loc[~excluded_mask(output)].copy().reset_index(drop=True)


def _as_timestamp(value: object, *, label: str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise PortfolioContractError(f"유효하지 않은 {label}: {value!r}")
    return pd.Timestamp(parsed).normalize()


def select_liquidity_core(
    market: pd.DataFrame,
    membership: pd.DataFrame,
    signal_date: object,
    *,
    rules: Phase5SPortfolioRules = DEFAULT_RULES,
) -> pd.DataFrame:
    """``t``까지 trailing-20 중앙 거래대금 상위 core를 고른다.

    시가총액 열은 존재하더라도 읽지 않는다. 각 후보는 선택에 사용한 전역
    20개 세션 모두에 양의 close와 volume이 있어야 한다.
    """

    for frame, required, name in (
        (market, {"date", "ticker", "close", "volume"}, "market"),
        (membership, {"date", "ticker"}, "membership"),
    ):
        missing = required.difference(frame.columns)
        if missing:
            raise PortfolioContractError(f"{name} 필수 열 누락: {sorted(missing)}")

    signal = _as_timestamp(signal_date, label="signal_date")
    members = membership.copy()
    members["_date"] = pd.to_datetime(members["date"], errors="coerce").dt.normalize()
    if members["_date"].isna().any():
        raise PortfolioContractError("membership date 파싱 실패")
    members["ticker"] = _normalized_tickers(members)
    members = members.loc[members["_date"].eq(signal)].copy()
    if members.empty:
        raise PortfolioContractError("신호일 PIT membership가 없습니다.")
    members = filter_excluded_securities(members)
    if members["ticker"].duplicated().any():
        raise PortfolioContractError("신호일 membership ticker가 중복됩니다.")

    prices = market[["date", "ticker", "close", "volume"]].copy()
    prices["_date"] = pd.to_datetime(prices["date"], errors="coerce").dt.normalize()
    if prices["_date"].isna().any():
        raise PortfolioContractError("market date 파싱 실패")
    prices["ticker"] = _normalized_tickers(prices)
    prices = prices.loc[
        prices["ticker"].isin(set(members["ticker"])) & prices["_date"].le(signal)
    ].copy()
    if prices.duplicated(["_date", "ticker"]).any():
        raise PortfolioContractError("market date/ticker가 중복됩니다.")

    sessions = sorted(prices["_date"].drop_duplicates())
    if signal not in sessions:
        raise PortfolioContractError("신호일 market 관측치가 없습니다.")
    if len(sessions) < rules.lookback_sessions:
        raise PortfolioContractError("trailing liquidity lookback 세션이 부족합니다.")
    selected_sessions = sessions[-rules.lookback_sessions :]
    prices = prices.loc[prices["_date"].isin(selected_sessions)].copy()
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce")
    valid = (
        prices["close"].map(math.isfinite)
        & prices["volume"].map(math.isfinite)
        & prices["close"].gt(0)
        & prices["volume"].gt(0)
    )
    prices = prices.loc[valid].copy()
    prices["trading_value"] = prices["close"] * prices["volume"]

    grouped = prices.groupby("ticker", sort=False)["trading_value"].agg(["count", "median"])
    grouped = grouped.loc[grouped["count"].eq(rules.lookback_sessions)].reset_index()
    grouped = grouped.rename(columns={"median": "median_trading_value_20"})
    grouped = grouped.sort_values(
        ["median_trading_value_20", "ticker"], ascending=[False, True], kind="mergesort"
    ).head(rules.core_size)
    if len(grouped) != rules.core_size:
        raise PortfolioContractError(
            f"유효한 liquidity core가 {len(grouped)}개로, 동결된 {rules.core_size}개보다 적습니다."
        )

    identity_columns = ["ticker"] + (["security_id"] if "security_id" in members.columns else [])
    output = grouped.merge(members[identity_columns], on="ticker", how="left", validate="one_to_one")
    output.insert(0, "signal_date", signal.date().isoformat())
    output["liquidity_rank"] = range(1, len(output) + 1)
    return output.reset_index(drop=True)


def _validated_core(core: pd.DataFrame, rules: Phase5SPortfolioRules) -> pd.DataFrame:
    if "ticker" not in core.columns:
        raise PortfolioContractError("core에 ticker 열이 없습니다.")
    output = core.copy()
    output["ticker"] = _normalized_tickers(output)
    if len(output) != rules.core_size or output["ticker"].nunique() != rules.core_size:
        raise PortfolioContractError(f"core는 중복 없는 {rules.core_size}개 종목이어야 합니다.")
    if excluded_mask(output).any():
        raise PortfolioContractError("제외 security가 core에 포함됐습니다.")
    return output


def build_phase5s_targets(
    core: pd.DataFrame,
    scores: pd.DataFrame,
    *,
    score_column: str = "score",
    rules: Phase5SPortfolioRules = DEFAULT_RULES,
) -> pd.DataFrame:
    """core 70%와 점수 상위 10개 tilt 20%의 목표비중을 만든다."""

    core_frame = _validated_core(core, rules)
    if not {"ticker", score_column}.issubset(scores.columns):
        raise PortfolioContractError("scores에 ticker 또는 score 열이 없습니다.")
    score_frame = scores[["ticker", score_column]].copy()
    score_frame["ticker"] = _normalized_tickers(score_frame)
    if score_frame["ticker"].duplicated().any():
        raise PortfolioContractError("점수 ticker가 중복됩니다.")
    score_frame[score_column] = pd.to_numeric(score_frame[score_column], errors="coerce")
    if not score_frame[score_column].map(math.isfinite).all():
        raise PortfolioContractError("점수는 모두 유한한 수여야 합니다.")

    output = core_frame.merge(score_frame, on="ticker", how="left", validate="one_to_one")
    if output[score_column].isna().any():
        raise PortfolioContractError("core의 일부 종목에 점수가 없습니다.")
    ranked = output.sort_values([score_column, "ticker"], ascending=[False, True], kind="mergesort")
    rank_map = {ticker: rank for rank, ticker in enumerate(ranked["ticker"], start=1)}
    output["decision_score"] = output.pop(score_column)
    output["decision_rank"] = output["ticker"].map(rank_map).astype(int)
    output["base_weight"] = [rules.core_weight] * len(output)
    output["alpha_weight"] = output["decision_rank"].map(
        lambda rank: rules.alpha_increment if rank <= rules.alpha_size else Decimal("0")
    )
    output["target_weight"] = output["base_weight"] + output["alpha_weight"]
    if sum(output["target_weight"], Decimal("0")) != rules.stock_exposure:
        raise AssertionError("Phase 5S 목표 주식노출 합계가 동결값과 다릅니다.")
    return output.sort_values(["decision_rank", "ticker"], kind="mergesort").reset_index(drop=True)


def build_neutral_core_targets(
    core: pd.DataFrame,
    *,
    rules: Phase5SPortfolioRules = DEFAULT_RULES,
) -> pd.DataFrame:
    """같은 Top50을 각 1.8%로 보유하는 NEUTRAL_CORE 목표를 만든다."""

    output = _validated_core(core, rules)
    output["target_weight"] = [rules.neutral_weight] * len(output)
    if sum(output["target_weight"], Decimal("0")) != rules.stock_exposure:
        raise AssertionError("NEUTRAL_CORE 목표 주식노출 합계가 동결값과 다릅니다.")
    return output.sort_values("ticker", kind="mergesort").reset_index(drop=True)


def build_causal_buy_orders(
    targets: pd.DataFrame,
    signal_closes: pd.DataFrame,
    *,
    signal_date: date,
    execute_date: date,
    strategy_name: str = "PHASE5S",
    rules: Phase5SPortfolioRules = DEFAULT_RULES,
) -> tuple[Order, ...]:
    """신호일 종가만으로 t+1 one-sided buy-limit 주문을 동결한다."""

    if signal_date >= execute_date:
        raise PortfolioContractError("execute_date는 signal_date보다 뒤여야 합니다.")
    if not {"ticker", "target_weight"}.issubset(targets.columns):
        raise PortfolioContractError("targets 필수 열 누락")
    if not {"ticker", "close"}.issubset(signal_closes.columns):
        raise PortfolioContractError("signal_closes 필수 열 누락")

    target_frame = targets.copy()
    target_frame["ticker"] = _normalized_tickers(target_frame)
    if target_frame["ticker"].duplicated().any() or excluded_mask(target_frame).any():
        raise PortfolioContractError("목표비중에 중복 또는 제외 security가 있습니다.")
    target_frame["target_weight"] = target_frame["target_weight"].map(
        lambda value: value if isinstance(value, Decimal) else Decimal(str(value))
    )
    if any(weight <= 0 or weight > 1 for weight in target_frame["target_weight"]):
        raise PortfolioContractError("target_weight는 (0, 1] 범위여야 합니다.")
    if sum(target_frame["target_weight"], Decimal("0")) > Decimal("1"):
        raise PortfolioContractError("목표비중 합계가 1을 초과합니다.")

    closes = signal_closes.copy()
    if "date" in closes.columns:
        close_dates = pd.to_datetime(closes["date"], errors="coerce").dt.date
        if close_dates.isna().any() or not close_dates.eq(signal_date).all():
            raise PortfolioContractError("signal_closes에는 신호일 행만 허용됩니다.")
    closes["ticker"] = _normalized_tickers(closes)
    if closes["ticker"].duplicated().any():
        raise PortfolioContractError("signal close ticker가 중복됩니다.")
    closes["close"] = pd.to_numeric(closes["close"], errors="coerce")
    if not (closes["close"].map(math.isfinite) & closes["close"].gt(0)).all():
        raise PortfolioContractError("신호일 종가는 양의 유한값이어야 합니다.")
    joined = target_frame.merge(closes[["ticker", "close"]], on="ticker", how="left", validate="one_to_one")
    if joined["close"].isna().any():
        raise PortfolioContractError("목표 종목의 신호일 종가가 없습니다.")
    if "decision_rank" in joined.columns:
        joined = joined.sort_values(["decision_rank", "ticker"], kind="mergesort")
    else:
        joined = joined.sort_values("ticker", kind="mergesort")

    clean_strategy = re.sub(r"[^A-Za-z0-9_-]+", "_", strategy_name).strip("_") or "PHASE5S"
    orders: list[Order] = []
    for priority, row in enumerate(joined.itertuples(index=False)):
        close = Decimal(str(row.close))
        orders.append(
            Order(
                order_id=f"P5S:{clean_strategy}:{signal_date.isoformat()}:{row.ticker}",
                signal_date=signal_date,
                execute_date=execute_date,
                security_id=row.ticker,
                side=Side.BUY,
                target_weight=row.target_weight,
                priority=priority,
                limit_price=close * rules.limit_multiplier,
                max_holding_sessions=rules.maximum_holding_sessions,
                reason=f"PHASE5S_{clean_strategy}",
            )
        )
    return tuple(orders)
