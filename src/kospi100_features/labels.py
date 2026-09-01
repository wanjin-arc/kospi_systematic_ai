from __future__ import annotations

import numpy as np
import pandas as pd

from kospi100_baseline.features import MECHANICAL, _feature_segments


LABEL_COLUMN = "forward_excess_log_return_10"


def _adjusted_open(full_history: pd.DataFrame, actions: pd.DataFrame) -> pd.Series:
    adjusted = pd.to_numeric(full_history["open"], errors="coerce").astype(float).copy()
    mechanical = actions.loc[actions["feature_handling"].eq(MECHANICAL)]
    for action in mechanical.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        factor = float(action.price_multiplier)
        mask = full_history["security_id"].eq(action.security_id) & full_history["date"].lt(action.feature_boundary_date)
        adjusted.loc[mask] *= factor
    adjusted.loc[~np.isfinite(adjusted) | adjusted.le(0)] = np.nan
    return adjusted


def attach_forward_label(
    feature_frame: pd.DataFrame,
    full_history: pd.DataFrame,
    index: pd.DataFrame,
    actions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    calendar = index[["date", "open"]].copy().sort_values("date", kind="mergesort").reset_index(drop=True)
    calendar["entry_date"] = calendar["date"].shift(-1)
    calendar["exit_date"] = calendar["date"].shift(-11)
    date_map = calendar.set_index("date")[["entry_date", "exit_date"]]

    signals = feature_frame.copy()
    signals = signals.merge(date_map, left_on="date", right_index=True, how="left", validate="many_to_one")
    history = full_history.copy().sort_values(["security_id", "date"], kind="mergesort").reset_index(drop=True)
    history["feature_segment"] = _feature_segments(history, actions)
    history["adjusted_open"] = _adjusted_open(history, actions)
    if history.duplicated(["security_id", "date"]).any():
        raise ValueError("라벨 가격 데이터에 종목-날짜 중복이 있습니다")
    lookup = history[["security_id", "date", "adjusted_open", "tradable", "feature_segment"]]

    entry = lookup.rename(
        columns={
            "date": "entry_date",
            "adjusted_open": "entry_open",
            "tradable": "entry_tradable",
            "feature_segment": "entry_segment",
        }
    )
    exit_frame = lookup.rename(
        columns={
            "date": "exit_date",
            "adjusted_open": "exit_open",
            "tradable": "exit_tradable",
            "feature_segment": "exit_segment",
        }
    )
    signals = signals.merge(entry, on=["security_id", "entry_date"], how="left", validate="many_to_one")
    signals = signals.merge(exit_frame, on=["security_id", "exit_date"], how="left", validate="many_to_one")

    index_open = calendar.set_index("date")["open"]
    signals["index_entry_open"] = signals["entry_date"].map(index_open)
    signals["index_exit_open"] = signals["exit_date"].map(index_open)
    same_segment = (
        signals["feature_segment"].eq(signals["entry_segment"])
        & signals["feature_segment"].eq(signals["exit_segment"])
    )
    valid = (
        signals["phase4_eligible"]
        & signals["entry_tradable"].astype("boolean").fillna(False)
        & signals["exit_tradable"].astype("boolean").fillna(False)
        & same_segment
        & signals[["entry_open", "exit_open", "index_entry_open", "index_exit_open"]].notna().all(axis=1)
    )
    signals[LABEL_COLUMN] = np.nan
    signals.loc[valid, LABEL_COLUMN] = (
        np.log(signals.loc[valid, "exit_open"] / signals.loc[valid, "entry_open"])
        - np.log(signals.loc[valid, "index_exit_open"] / signals.loc[valid, "index_entry_open"])
    )
    timing_valid = signals.loc[signals[LABEL_COLUMN].notna(), "date"].lt(
        signals.loc[signals[LABEL_COLUMN].notna(), "entry_date"]
    ) & signals.loc[signals[LABEL_COLUMN].notna(), "entry_date"].lt(
        signals.loc[signals[LABEL_COLUMN].notna(), "exit_date"]
    )
    if not timing_valid.all():
        raise AssertionError("라벨 시점 불변조건이 실패했습니다")
    audit = {
        "label_name": LABEL_COLUMN,
        "eligible_signal_rows": int(signals["phase4_eligible"].sum()),
        "complete_label_rows": int(signals[LABEL_COLUMN].notna().sum()),
        "reset_crossing_rows_excluded": int((signals["phase4_eligible"] & ~same_segment).sum()),
        "entry_is_after_signal": True,
        "exit_is_after_entry": True,
        "same_day_execution": False,
    }
    return signals, audit
