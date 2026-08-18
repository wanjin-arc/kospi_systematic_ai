from __future__ import annotations

import math
import statistics
from collections import defaultdict
from decimal import Decimal

from .types import RunResult, Side, ZERO


def _decimal(value: float | int | Decimal | None) -> Decimal | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        return None
    return Decimal(str(value))


def calculate_metrics(result: RunResult) -> dict[str, Decimal | int | str | None]:
    if not result.equity_curve:
        raise ValueError("equity curve is empty")
    equity = [result.initial_cash] + [point.equity for point in result.equity_curve]
    returns = [float(point.daily_return) for point in result.equity_curve]
    total_return = result.equity_curve[-1].equity / result.initial_cash - Decimal("1")

    elapsed_days = (result.equity_curve[-1].session - result.equity_curve[0].session).days
    cagr: float | None = None
    if elapsed_days > 0 and result.equity_curve[-1].equity > ZERO:
        cagr = float(result.equity_curve[-1].equity / result.initial_cash) ** (365.2425 / elapsed_days) - 1.0

    volatility = statistics.stdev(returns) * math.sqrt(252) if len(returns) >= 2 else None
    mean_return = statistics.fmean(returns) if returns else 0.0
    sharpe = mean_return / statistics.stdev(returns) * math.sqrt(252) if len(returns) >= 2 and statistics.stdev(returns) > 0 else None
    downside = math.sqrt(statistics.fmean([min(value, 0.0) ** 2 for value in returns])) if returns else 0.0
    sortino = mean_return / downside * math.sqrt(252) if downside > 0 else None

    peak = equity[0]
    max_drawdown = ZERO
    max_duration = 0
    current_duration = 0
    for value in equity[1:]:
        if value >= peak:
            peak = value
            current_duration = 0
        else:
            drawdown = value / peak - Decimal("1")
            max_drawdown = min(max_drawdown, drawdown)
            current_duration += 1
            max_duration = max(max_duration, current_duration)
    calmar = cagr / abs(float(max_drawdown)) if cagr is not None and max_drawdown < ZERO else None

    commissions = sum((fill.commission for fill in result.fills), ZERO)
    transaction_tax = sum((fill.transaction_tax for fill in result.fills), ZERO)
    rural_tax = sum((fill.rural_special_tax for fill in result.fills), ZERO)
    slippage = sum((fill.slippage_cost for fill in result.fills), ZERO)
    gross_traded = sum((fill.gross_notional for fill in result.fills), ZERO)
    average_equity = sum((point.equity for point in result.equity_curve), ZERO) / len(result.equity_curve)
    turnover = gross_traded / average_equity if average_equity else ZERO
    average_cash_weight = sum((point.cash_weight for point in result.equity_curve), ZERO) / len(result.equity_curve)

    wins = [trade for trade in result.closed_trades if trade.net_pnl > ZERO]
    losses = [trade for trade in result.closed_trades if trade.net_pnl < ZERO]
    win_rate = Decimal(len(wins)) / len(result.closed_trades) if result.closed_trades else None
    average_win = sum((item.net_pnl for item in wins), ZERO) / len(wins) if wins else None
    average_loss = sum((item.net_pnl for item in losses), ZERO) / len(losses) if losses else None
    payoff = average_win / abs(average_loss) if average_win is not None and average_loss not in (None, ZERO) else None
    average_holding = (
        Decimal(sum(item.holding_sessions for item in result.closed_trades)) / len(result.closed_trades)
        if result.closed_trades
        else None
    )

    benchmark_values = [point.benchmark_close for point in result.equity_curve if point.benchmark_close is not None]
    benchmark_total: Decimal | None = None
    annualized_alpha: Decimal | None = None
    if len(benchmark_values) >= 2 and benchmark_values[0] and benchmark_values[-1]:
        benchmark_total = benchmark_values[-1] / benchmark_values[0] - Decimal("1")
        if elapsed_days > 0:
            benchmark_cagr = float(benchmark_values[-1] / benchmark_values[0]) ** (365.2425 / elapsed_days) - 1.0
            annualized_alpha = _decimal(cagr - benchmark_cagr if cagr is not None else None)  # type: ignore[assignment]

    annual_end: dict[int, Decimal] = {}
    for point in result.equity_curve:
        annual_end[point.session.year] = point.equity
    annual_returns: dict[str, str] = {}
    prior_year_end = result.initial_cash
    for year in sorted(annual_end):
        annual_returns[str(year)] = str(annual_end[year] / prior_year_end - Decimal("1"))
        prior_year_end = annual_end[year]

    status_counts: dict[str, int] = defaultdict(int)
    for event in result.order_events:
        status_counts[event.status.value] += 1

    return {
        "sessions": len(result.equity_curve),
        "initial_equity": result.initial_cash,
        "final_equity": result.equity_curve[-1].equity,
        "total_return": total_return,
        "cagr": _decimal(cagr),
        "annualized_volatility": _decimal(volatility),
        "sharpe_zero_rf": _decimal(sharpe),
        "sortino_zero_target": _decimal(sortino),
        "max_drawdown": max_drawdown,
        "max_drawdown_duration_sessions": max_duration,
        "calmar": _decimal(calmar),
        "benchmark_total_return": benchmark_total,
        "annualized_alpha_vs_benchmark": annualized_alpha,
        "fills": len(result.fills),
        "buy_fills": sum(1 for fill in result.fills if fill.side is Side.BUY),
        "sell_fills": sum(1 for fill in result.fills if fill.side is Side.SELL),
        "closed_trades": len(result.closed_trades),
        "win_rate": win_rate,
        "average_win_krw": average_win,
        "average_loss_krw": average_loss,
        "payoff_ratio": payoff,
        "average_holding_sessions": average_holding,
        "gross_traded_notional": gross_traded,
        "turnover_on_average_equity": turnover,
        "commission_total": commissions,
        "transaction_tax_total": transaction_tax,
        "rural_special_tax_total": rural_tax,
        "slippage_cost_total": slippage,
        "all_explicit_costs": commissions + transaction_tax + rural_tax + slippage,
        "average_cash_weight": average_cash_weight,
        "stale_position_marks": sum(point.stale_position_count for point in result.equity_curve),
        "annual_returns_json": json_dumps(annual_returns),
        "order_status_counts_json": json_dumps(dict(sorted(status_counts.items()))),
        "reconciliation": "PASS" if result.reconciliation.passed else "FAIL",
    }


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
