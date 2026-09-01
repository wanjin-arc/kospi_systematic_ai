"""Phase 5S reset/action-aware 20-session 비용 차감 active-return 라벨."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kospi100_backtest.costs import CostSchedule

from .config import guard_path


EXCLUDED_TICKERS = frozenset({"005930", "000660"})
EXCLUDED_SECURITY_IDS = frozenset({"KRX_COMMON:005930", "KRX_COMMON:000660"})
LABEL_COLUMNS = (
    "target_stock_gross_return_20",
    "target_stock_net_return_20",
    "target_index_return_20",
    "target_net_active_20",
    "target_mae_20",
    "target_quality_20",
)


def _schedule(value: CostSchedule | Path | str) -> CostSchedule:
    if isinstance(value, CostSchedule):
        return value
    return CostSchedule.from_csv(guard_path(Path(value)))


def _normalise_dates(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if "date" not in frame:
        raise ValueError(f"{name}에 date 열이 없습니다.")
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"], errors="raise").dt.date.astype(str)
    return output


def _validate_sessions(sessions: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    values = tuple(str(value) for value in sessions)
    if not values or values != tuple(sorted(set(values))):
        raise ValueError("라벨 exchange sessions은 중복 없는 오름차순이어야 합니다.")
    return values


def attach_reset_safe_labels(
    signals: pd.DataFrame,
    market: pd.DataFrame,
    sessions: tuple[str, ...] | list[str],
    index: pd.DataFrame,
    membership: pd.DataFrame,
    cost_schedule: CostSchedule | Path | str,
    *,
    horizon: int = 20,
    downside_penalty: float = 0.5,
    commission_rate: float = 0.0002,
    slippage_rate: float = 0.001,
    cost_multiplier: float = 1.0,
    gap_limit_rate: float = 0.05,
    label_start: str = "2011-01-03",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    입력 score 행을 절대 제거하지 않고 라벨 유효성과 무효 사유를 추가한다.

    signal ``t``의 다음 세션 시가로 진입하고 ``t+21`` 세션 시가로
    종료하므로 ``horizon=20``은 정확히 20개 보유 세션을 의미한다.
    """

    if horizon != 20:
        raise ValueError("Phase 5S 라벨 horizon은 20세션으로 동결됩니다.")
    if downside_penalty != 0.5:
        raise ValueError("Phase 5S downside penalty는 0.5로 동결됩니다.")
    if min(commission_rate, slippage_rate, cost_multiplier, gap_limit_rate) < 0 or cost_multiplier <= 0:
        raise ValueError("비용·gap 인자는 유효한 음이 아닌 값이어야 합니다.")
    calendar = _validate_sessions(sessions)
    session_number = {day: number for number, day in enumerate(calendar)}
    signals_work = _normalise_dates(signals, "signals")
    market_work = _normalise_dates(market, "market")
    index_work = _normalise_dates(index, "index")
    membership_work = _normalise_dates(membership, "membership")
    required_signal = {"date", "ticker"}
    required_market = {"date", "ticker", "open", "high", "low", "close"}
    if not required_signal.issubset(signals_work):
        raise ValueError(f"signals 열 누락: {sorted(required_signal - set(signals_work))}")
    if not required_market.issubset(market_work):
        raise ValueError(f"market 열 누락: {sorted(required_market - set(market_work))}")
    if not {"date", "open"}.issubset(index_work):
        raise ValueError("index에 date/open 열이 필요합니다.")
    if not {"date", "ticker"}.issubset(membership_work):
        raise ValueError("membership에 date/ticker 열이 필요합니다.")
    for name, frame in (
        ("signals", signals_work),
        ("market", market_work),
        ("membership", membership_work),
    ):
        frame["ticker"] = frame["ticker"].astype(str).str.strip()
        invalid_ticker = ~frame["ticker"].str.fullmatch(r"\d{6}", na=False)
        if bool(invalid_ticker.any()):
            raise ValueError(f"{name}에 비정규 raw ticker가 있습니다.")
    if signals_work.duplicated(["date", "ticker"]).any():
        raise ValueError("signals에 종목-날짜 중복이 있습니다.")
    if market_work.duplicated(["date", "ticker"]).any():
        raise ValueError("market에 종목-날짜 중복이 있습니다.")
    if index_work.duplicated("date").any():
        raise ValueError("index에 날짜 중복이 있습니다.")
    if membership_work.duplicated(["date", "ticker"]).any():
        raise ValueError("membership에 종목-날짜 중복이 있습니다.")

    signals_work["security_id"] = signals_work.get(
        "security_id", "KRX_COMMON:" + signals_work["ticker"]
    )
    excluded = signals_work["ticker"].isin(EXCLUDED_TICKERS) | signals_work["security_id"].astype(str).isin(EXCLUDED_SECURITY_IDS)
    if excluded.any():
        raise ValueError("제외 security는 Phase 5S 라벨 입력에 들어올 수 없습니다.")

    for column in ("open", "high", "low", "close"):
        market_work[column] = pd.to_numeric(market_work[column], errors="coerce")
    for boundary in (
        "unresolved_share_change_candidate",
        "listed_shares_observation_gap",
    ):
        if boundary not in market_work:
            raise ValueError(f"라벨 market 입력에 share-change 경계 열이 없습니다: {boundary}")
    if "mechanical_reset" not in market_work:
        market_work["mechanical_reset"] = False
    if "unresolved_action" not in market_work:
        market_work["unresolved_action"] = False
    market_work["unresolved_share_change_candidate"] = (
        market_work["unresolved_share_change_candidate"]
        .astype("boolean")
        .fillna(True)
        .astype(bool)
    )
    market_work["listed_shares_observation_gap"] = (
        market_work["listed_shares_observation_gap"]
        .astype("boolean")
        .fillna(True)
        .astype(bool)
    )
    market_work["mechanical_reset"] = market_work["mechanical_reset"].astype("boolean").fillna(True).astype(bool)
    if bool((market_work["mechanical_reset"] & ~market_work["unresolved_share_change_candidate"]).any()):
        raise ValueError("mechanical_reset은 share-change candidate의 부분집합이어야 합니다.")
    market_work["unresolved_action"] = market_work["unresolved_action"].astype("boolean").fillna(True).astype(bool)
    market_work["security_id"] = market_work.get("security_id", "KRX_COMMON:" + market_work["ticker"])
    membership_work["security_id"] = membership_work.get("security_id", "KRX_COMMON:" + membership_work["ticker"])
    index_work["open"] = pd.to_numeric(index_work["open"], errors="coerce")
    index_open = index_work.set_index("date")["open"].reindex(calendar).to_numpy(float)
    member_identity = {
        (row.date, row.ticker): str(row.security_id)
        for row in membership_work[["date", "ticker", "security_id"]].itertuples(index=False)
    }
    schedule = _schedule(cost_schedule)
    commission = commission_rate * cost_multiplier
    slippage = slippage_rate * cost_multiplier
    if commission >= 1 or slippage >= 1:
        raise ValueError("비용 stress 인자가 비정상적입니다.")

    output = signals_work.copy()
    output["entry_date"] = pd.NA
    output["exit_date"] = pd.NA
    output["entry_limit_price"] = np.nan
    output["entry_fillable"] = False
    output["sell_transaction_tax_rate"] = np.nan
    output["sell_rural_special_tax_rate"] = np.nan
    for column in LABEL_COLUMNS:
        output[column] = np.nan
    output["label_valid"] = False
    output["label_invalid_reason"] = ""

    values: dict[str, list[Any]] = {column: [None] * len(output) for column in output.columns if column not in signals_work.columns}
    # 추가 열을 list로 계산해 원래 index·행 순서를 변경하지 않는다.
    for column in ("entry_limit_price", "sell_transaction_tax_rate", "sell_rural_special_tax_rate", *LABEL_COLUMNS):
        values[column] = [np.nan] * len(output)
    values["entry_fillable"] = [False] * len(output)
    values["label_valid"] = [False] * len(output)
    values["label_invalid_reason"] = [""] * len(output)

    market_groups = {
        ticker: group.set_index("date").reindex(calendar)
        for ticker, group in market_work.groupby("ticker", sort=False)
        if ticker in set(output["ticker"])
    }
    invalid_counts: dict[str, int] = {}
    label_start_date = date.fromisoformat(label_start)
    tax_dates_used: set[str] = set()
    for position, row in enumerate(output[["date", "ticker", "security_id"]].itertuples(index=False)):
        reasons: list[str] = []
        signal_day = str(row.date)
        signal_position = session_number.get(signal_day)
        if signal_position is None:
            reasons.append("SIGNAL_NOT_EXCHANGE_SESSION")
        elif date.fromisoformat(signal_day) < label_start_date:
            reasons.append("BEFORE_VERIFIED_COST_WINDOW")
        elif signal_position + horizon + 1 >= len(calendar):
            reasons.append("INSUFFICIENT_FUTURE_SESSIONS")
        if signal_position is None or signal_position + horizon + 1 >= len(calendar):
            values["label_invalid_reason"][position] = ";".join(reasons)
            for reason in reasons:
                invalid_counts[reason] = invalid_counts.get(reason, 0) + 1
            continue

        entry_position = signal_position + 1
        exit_position = signal_position + horizon + 1
        entry_day, exit_day = calendar[entry_position], calendar[exit_position]
        values["entry_date"][position] = entry_day
        values["exit_date"][position] = exit_day
        # 비용 기간에 들어온 모든 라벨은 다른 무효 사유가 있어도 매도일 세율을 검증한다.
        if date.fromisoformat(signal_day) >= label_start_date:
            transaction_tax, rural_tax = schedule.rates_on(date.fromisoformat(exit_day))
            transaction_rate, rural_rate = float(transaction_tax), float(rural_tax)
            values["sell_transaction_tax_rate"][position] = transaction_rate
            values["sell_rural_special_tax_rate"][position] = rural_rate
            tax_dates_used.add(exit_day)
        else:
            transaction_rate = rural_rate = np.nan

        ticker_frame = market_groups.get(row.ticker)
        if ticker_frame is None:
            reasons.append("MISSING_REQUIRED_OHLC")
        else:
            window = ticker_frame.iloc[signal_position:exit_position + 1]
            expected_security_id = str(row.security_id)
            price_identity = window["security_id"].astype(str).eq(expected_security_id)
            required_prices = window[["open", "high", "low", "close"]]
            finite = np.isfinite(required_prices.to_numpy(float)).all()
            positive = required_prices.gt(0).all(axis=None)
            coherent = (
                window["high"].ge(window[["open", "close"]].max(axis=1)).all()
                and window["low"].le(window[["open", "close"]].min(axis=1)).all()
            )
            if not bool(price_identity.all()):
                reasons.append("PRICE_IDENTITY_GAP")
            if not bool(finite and positive and coherent):
                reasons.append("MISSING_REQUIRED_OHLC")
            if bool(window["mechanical_reset"].any()):
                reasons.append("RESET_CROSSING")
            if bool(window["unresolved_share_change_candidate"].any()):
                reasons.append("UNRESOLVED_SHARE_CHANGE_CROSSING")
            if bool(window["listed_shares_observation_gap"].any()):
                reasons.append("LISTED_SHARES_OBSERVATION_GAP")
            if bool(window["unresolved_action"].any()):
                reasons.append("UNRESOLVED_ACTION_CROSSING")
            member_ok = all(
                member_identity.get((day, row.ticker)) == expected_security_id
                for day in calendar[signal_position:exit_position + 1]
            )
            if not member_ok:
                reasons.append("MEMBERSHIP_OR_IDENTITY_GAP")
            if finite and positive and coherent:
                signal_close = float(ticker_frame.iloc[signal_position]["close"])
                entry_open = float(ticker_frame.iloc[entry_position]["open"])
                exit_open = float(ticker_frame.iloc[exit_position]["open"])
                limit_price = signal_close * (1.0 + gap_limit_rate)
                fillable = entry_open <= limit_price
                values["entry_limit_price"][position] = limit_price
                values["entry_fillable"][position] = bool(fillable)
                if not fillable:
                    reasons.append("UNFILLED_GAP_LIMIT")
                index_entry, index_exit = index_open[entry_position], index_open[exit_position]
                if not (np.isfinite(index_entry) and index_entry > 0 and np.isfinite(index_exit) and index_exit > 0):
                    reasons.append("INDEX_OPEN_MISSING")
                if not reasons:
                    gross = exit_open / entry_open - 1.0
                    buy_outlay = entry_open * (1.0 + slippage) * (1.0 + commission)
                    sell_proceeds = exit_open * (1.0 - slippage) * (
                        1.0 - commission - transaction_rate - rural_rate
                    )
                    if buy_outlay <= 0 or sell_proceeds <= 0:
                        raise ValueError("라벨 비용 계산이 비정상적입니다.")
                    stock_net = sell_proceeds / buy_outlay - 1.0
                    index_return = index_exit / index_entry - 1.0
                    lows = ticker_frame.iloc[entry_position:exit_position]["low"].to_numpy(float)
                    mae = max(0.0, 1.0 - float(np.min(lows)) / entry_open)
                    active = stock_net - index_return
                    quality = active - downside_penalty * mae
                    values["target_stock_gross_return_20"][position] = gross
                    values["target_stock_net_return_20"][position] = stock_net
                    values["target_index_return_20"][position] = index_return
                    values["target_net_active_20"][position] = active
                    values["target_mae_20"][position] = mae
                    values["target_quality_20"][position] = quality
                    values["label_valid"][position] = True
        values["label_invalid_reason"][position] = ";".join(dict.fromkeys(reasons))
        for reason in dict.fromkeys(reasons):
            invalid_counts[reason] = invalid_counts.get(reason, 0) + 1

    for column, column_values in values.items():
        output[column] = column_values
    output["label_valid"] = output["label_valid"].astype(bool)
    if len(output) != len(signals) or not output[["date", "ticker"]].reset_index(drop=True).equals(
        signals_work[["date", "ticker"]].reset_index(drop=True)
    ):
        raise AssertionError("라벨 availability가 score universe 행을 변경했습니다.")
    valid = output["label_valid"]
    if output.loc[valid, list(LABEL_COLUMNS)].isna().any(axis=None):
        raise AssertionError("유효 라벨에 결측 값이 있습니다.")
    if output.loc[~valid, list(LABEL_COLUMNS)].notna().any(axis=None):
        raise AssertionError("무효 라벨에 target 값이 남아 있습니다.")
    audit: dict[str, Any] = {
        "signal_rows": int(len(signals)),
        "output_rows": int(len(output)),
        "complete_label_rows": int(valid.sum()),
        "invalid_label_rows": int((~valid).sum()),
        "invalid_reason_counts": dict(sorted(invalid_counts.items())),
        "reset_crossing_rows_excluded": int(output["label_invalid_reason"].str.contains("RESET_CROSSING", regex=False).sum()),
        "unresolved_share_change_crossing_rows_excluded": int(
            output["label_invalid_reason"].str.contains(
                "UNRESOLVED_SHARE_CHANGE_CROSSING", regex=False
            ).sum()
        ),
        "listed_shares_observation_gap_rows_excluded": int(
            output["label_invalid_reason"].str.contains(
                "LISTED_SHARES_OBSERVATION_GAP", regex=False
            ).sum()
        ),
        "valid_label_share_change_crossing_rows": int(
            (
                output["label_valid"]
                & output["label_invalid_reason"].str.contains(
                    "UNRESOLVED_SHARE_CHANGE_CROSSING", regex=False
                )
            ).sum()
        ),
        "valid_label_listed_shares_gap_rows": int(
            (
                output["label_valid"]
                & output["label_invalid_reason"].str.contains(
                    "LISTED_SHARES_OBSERVATION_GAP", regex=False
                )
            ).sum()
        ),
        "unresolved_action_rows_excluded": int(output["label_invalid_reason"].str.contains("UNRESOLVED_ACTION_CROSSING", regex=False).sum()),
        "membership_or_identity_gap_rows_excluded": int(output["label_invalid_reason"].str.contains("MEMBERSHIP_OR_IDENTITY_GAP", regex=False).sum()),
        "unfilled_gap_limit_rows": int(output["label_invalid_reason"].str.contains("UNFILLED_GAP_LIMIT", regex=False).sum()),
        "score_universe_rows_unchanged": True,
        "future_label_availability_used_for_scoring": False,
        "entry_offset_sessions": 1,
        "exit_offset_sessions": horizon + 1,
        "holding_sessions": horizon,
        "commission_rate_per_side": commission,
        "slippage_rate_per_side": slippage,
        "tax_stress_multiplier": 1.0,
        "verified_sell_tax_dates_used": sorted(tax_dates_used),
    }
    return output, audit
