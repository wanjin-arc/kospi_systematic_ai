from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from kospi100_ranking.config import Period
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.portfolio import build_context, run_portfolio

from .config import MultifactorConfig


@dataclass(frozen=True)
class MultifactorPortfolioEvaluation:
    metrics: pd.DataFrame
    accepted_candidate: str | None
    diagnostic_best_candidate: str
    gate: dict[str, object]


def _priority(row: pd.Series, order: tuple[str, ...]) -> tuple[float, float, float, float, int]:
    sharpe = float(row["sharpe_zero_rf"]) if pd.notna(row["sharpe_zero_rf"]) else float("-inf")
    return (
        float(row["net_excess_return"]),
        sharpe,
        float(row["max_drawdown"]),
        -float(row["turnover_on_average_equity"]),
        -order.index(str(row["candidate"])),
    )


def evaluate_internal_portfolios(
    predictions: pd.DataFrame,
    bundle: SelectionBundle,
    config: MultifactorConfig,
) -> MultifactorPortfolioEvaluation:
    connected_period = Period("internal_validation_2015_2018", date(2015, 1, 1), date(2018, 12, 31))
    connected, unresolved = build_context(bundle, connected_period)
    rows: list[dict[str, object]] = []
    for candidate in config.candidate_order:
        candidate_predictions = predictions.loc[predictions["candidate"].eq(candidate)]
        for multiplier in config.stress_multipliers:
            rows.append(run_portfolio(candidate, candidate_predictions, connected, unresolved, config, multiplier))
        for fold in config.folds:
            context, fold_unresolved = build_context(bundle, fold.validation)
            fold_predictions = candidate_predictions.loc[candidate_predictions["fold"].eq(fold.name)]
            rows.append(run_portfolio(candidate, fold_predictions, context, fold_unresolved, config, 1))
    metrics = pd.DataFrame(rows)
    connected_base = metrics.loc[
        metrics["period"].eq(connected_period.name) & metrics["cost_multiplier"].eq(1)
    ].copy()
    annual = metrics.loc[
        metrics["period"].str.startswith("I") & metrics["cost_multiplier"].eq(1)
    ].copy()
    annual_counts = annual.groupby("candidate")["net_excess_return"].apply(
        lambda values: int((values.astype(float) >= 0.0).sum())
    )
    gate_rows: list[dict[str, object]] = []
    for row in connected_base.itertuples(index=False):
        count = int(annual_counts.get(row.candidate, 0))
        connected_positive = float(row.net_excess_return) > 0.0
        passed = connected_positive and count >= 4
        gate_rows.append(
            {
                "candidate": row.candidate,
                "connected_net_excess_return": row.net_excess_return,
                "nonnegative_annual_excess_folds": count,
                "required_nonnegative_annual_excess_folds": 4,
                "connected_positive": connected_positive,
                "passed_internal_gate": passed,
            }
        )
    gate_frame = pd.DataFrame(gate_rows)
    diagnostic_row = max((row for _, row in connected_base.iterrows()), key=lambda row: _priority(row, config.candidate_order))
    diagnostic = str(diagnostic_row["candidate"])
    eligible_names = set(gate_frame.loc[gate_frame["passed_internal_gate"], "candidate"])
    eligible = connected_base.loc[connected_base["candidate"].isin(eligible_names)]
    if eligible.empty:
        accepted = None
    else:
        accepted_row = max((row for _, row in eligible.iterrows()), key=lambda row: _priority(row, config.candidate_order))
        accepted = str(accepted_row["candidate"])
    selected_for_diagnostics = accepted or diagnostic
    for fold in config.folds:
        context, fold_unresolved = build_context(bundle, fold.validation)
        fold_predictions = predictions.loc[
            predictions["candidate"].eq(selected_for_diagnostics) & predictions["fold"].eq(fold.name)
        ]
        rows.append(run_portfolio(selected_for_diagnostics, fold_predictions, context, fold_unresolved, config, 2))
    metrics = pd.DataFrame(rows)
    gate = {
        "accepted_candidate": accepted,
        "diagnostic_best_candidate": diagnostic,
        "selected_for_model_artifact": selected_for_diagnostics,
        "status": "ACCEPTED_INTERNAL_GATE" if accepted else "REJECTED_NO_CANDIDATE_BEAT_BENCHMARK_GATE",
        "candidate_gate_rows": gate_rows,
        "development_test_authorized": False,
        "development_test_runs": 0,
    }
    return MultifactorPortfolioEvaluation(metrics, accepted, diagnostic, gate)
