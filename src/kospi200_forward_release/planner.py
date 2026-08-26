from __future__ import annotations

from typing import Any

import pandas as pd

from .contract import ContractError, validate_contract


_REQUIRED_COLUMNS = {
    "signal_date",
    "trade_date",
    "ticker",
    "agent_b_rank",
    "cnn_probability",
    "gap_from_previous_close",
}


def build_shadow_orders(signals: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """네트워크 호출 없이 t+1 시가용 주문 의도만 결정적으로 만든다."""
    validate_contract(config, release_ready=True)
    missing = _REQUIRED_COLUMNS - set(signals.columns)
    if missing:
        raise ContractError(f"필수 signal 열이 없습니다: {sorted(missing)}")

    frame = signals.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="raise")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    if (frame["trade_date"] <= frame["signal_date"]).any():
        raise ContractError("모든 주문일은 신호일보다 뒤여야 합니다.")

    d = config["agent_d"]
    eligible = frame.loc[
        (frame["agent_b_rank"].between(1, 30))
        & (frame["cnn_probability"] >= float(d["entry_probability_low"]))
        & (frame["gap_from_previous_close"].abs() <= float(d["gap_veto"]))
    ].copy()
    eligible["target_weight"] = float(d["target_weight_low"])
    eligible.loc[
        eligible["cnn_probability"] >= float(d["entry_probability_high"]), "target_weight"
    ] = float(d["target_weight_high"])
    eligible["side"] = "BUY"
    eligible["order_type"] = "MARKET_OPEN_INTENT"
    eligible["execution_mode"] = "SHADOW_ONLY"

    eligible = eligible.sort_values(
        ["trade_date", "cnn_probability", "agent_b_rank", "ticker"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    eligible = eligible.groupby("trade_date", sort=True, group_keys=False).head(
        int(d["maximum_positions"])
    )
    columns = [
        "signal_date",
        "trade_date",
        "ticker",
        "side",
        "target_weight",
        "order_type",
        "execution_mode",
        "agent_b_rank",
        "cnn_probability",
    ]
    return eligible.loc[:, columns].reset_index(drop=True)
