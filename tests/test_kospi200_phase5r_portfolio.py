import unittest
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from kospi100_backtest.costs import CostBand, CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.types import Bar, OrderStatus
from kospi200_phase5r.portfolio import (
    DEFAULT_RULES,
    PortfolioContractError,
    build_causal_buy_orders,
    build_neutral_core_targets,
    build_phase5r_targets,
    select_liquidity_core,
)


def _ticker(number: int) -> str:
    return f"{number:06d}"


def _synthetic_inputs():
    start = date(2023, 1, 2)
    sessions = [start + timedelta(days=index) for index in range(20)]
    tickers = [_ticker(index) for index in range(1, 53)] + ["005930", "000660"]
    membership = pd.DataFrame(
        [{"date": sessions[-1], "ticker": ticker, "security_id": f"KRX_COMMON:{ticker}"} for ticker in tickers]
    )
    market_rows = []
    for session in sessions:
        for index, ticker in enumerate(tickers, start=1):
            market_rows.append({
                "date": session,
                "ticker": ticker,
                "close": 100.0,
                "volume": float(index * 100),
                "market_cap": float((1000 - index) * 1_000_000),
            })
    return sessions, pd.DataFrame(market_rows), membership


class Phase5RPortfolioTests(unittest.TestCase):
    def test_top50_uses_only_trailing_median_value_and_excludes_two_names(self):
        sessions, market, membership = _synthetic_inputs()
        core = select_liquidity_core(market, membership, sessions[-1])
        self.assertEqual(len(core), 50)
        self.assertFalse({"005930", "000660"}.intersection(core["ticker"]))
        self.assertEqual(core.iloc[0]["ticker"], "000052")
        self.assertEqual(core.iloc[-1]["ticker"], "000003")

        changed_cap = market.copy()
        changed_cap["market_cap"] = list(reversed(changed_cap["market_cap"].tolist()))
        other = select_liquidity_core(changed_cap, membership, sessions[-1])
        self.assertEqual(core["ticker"].tolist(), other["ticker"].tolist())

    def test_future_rows_and_ties_cannot_change_signal_day_selection(self):
        sessions, market, membership = _synthetic_inputs()
        base = select_liquidity_core(market, membership, sessions[-1])
        future = market.iloc[:54].copy()
        future["date"] = sessions[-1] + timedelta(days=1)
        future["volume"] = 10**20
        with_future = select_liquidity_core(pd.concat([market, future], ignore_index=True), membership, sessions[-1])
        self.assertEqual(base["ticker"].tolist(), with_future["ticker"].tolist())

        tied_market = market.copy()
        tied_market["volume"] = 100.0
        tied = select_liquidity_core(tied_market, membership, sessions[-1])
        self.assertEqual(tied["ticker"].tolist(), [_ticker(index) for index in range(1, 51)])

    def test_phase5r_and_neutral_weights_are_exact_70_20_10_and_90_10(self):
        sessions, market, membership = _synthetic_inputs()
        core = select_liquidity_core(market, membership, sessions[-1])
        scores = pd.DataFrame({"ticker": core["ticker"], "score": range(len(core))})
        targets = build_phase5r_targets(core, scores)
        self.assertEqual(sum(targets["base_weight"], Decimal("0")), Decimal("0.700"))
        self.assertEqual(sum(targets["alpha_weight"], Decimal("0")), Decimal("0.200"))
        self.assertEqual(sum(targets["target_weight"], Decimal("0")), Decimal("0.900"))
        self.assertEqual((targets["target_weight"] == Decimal("0.034")).sum(), 10)
        self.assertEqual((targets["target_weight"] == Decimal("0.014")).sum(), 40)
        neutral = build_neutral_core_targets(core)
        self.assertEqual(sum(neutral["target_weight"], Decimal("0")), Decimal("0.900"))
        self.assertTrue((neutral["target_weight"] == Decimal("0.018")).all())
        self.assertEqual(DEFAULT_RULES.cash_weight, Decimal("0.10"))

    def test_orders_are_frozen_from_signal_close_with_one_sided_limit(self):
        core = pd.DataFrame({"ticker": [_ticker(index) for index in range(1, 51)]})
        neutral = build_neutral_core_targets(core)
        signal = date(2023, 1, 2)
        execute = date(2023, 1, 3)
        closes_one = pd.DataFrame({
            "date": [signal] * 50,
            "ticker": core["ticker"],
            "close": [Decimal("100")] * 50,
            "open": [1] * 50,
        })
        closes_two = closes_one.copy()
        closes_two["open"] = 10**9
        orders_one = build_causal_buy_orders(neutral, closes_one, signal_date=signal, execute_date=execute)
        orders_two = build_causal_buy_orders(neutral, closes_two, signal_date=signal, execute_date=execute)
        self.assertEqual(orders_one, orders_two)
        self.assertTrue(all(order.limit_price == Decimal("105.00") for order in orders_one))
        self.assertTrue(all(order.max_holding_sessions == 20 for order in orders_one))

        costs = ExecutionCostModel(
            CostSchedule((CostBand(date(2020, 1, 1), date(2025, 12, 31), Decimal("0"), Decimal("0")),)),
            commission_rate=Decimal("0"),
            buy_slippage_rate=Decimal("0"),
            sell_slippage_rate=Decimal("0"),
        )
        engine = BacktestEngine(EngineConfig(initial_cash=Decimal("1000000")), costs)
        two_targets = neutral.iloc[:2].copy()
        two_targets["target_weight"] = [Decimal("0.1"), Decimal("0.1")]
        two_closes = closes_one.iloc[:2].copy()
        two_orders = build_causal_buy_orders(two_targets, two_closes, signal_date=signal, execute_date=execute)
        bars = (
            Bar(execute, "000001", Decimal("106"), Decimal("106"), Decimal("106"), Decimal("106")),
            Bar(execute, "000002", Decimal("90"), Decimal("90"), Decimal("90"), Decimal("90")),
        )
        result = engine.run((signal, execute), bars, two_orders)
        statuses = {event.security_id: event.status for event in result.order_events}
        self.assertEqual(statuses["000001"], OrderStatus.UNFILLED_GAP_LIMIT)
        self.assertEqual(statuses["000002"], OrderStatus.FILLED)

    def test_excluded_ticker_or_security_id_fails_closed(self):
        core = pd.DataFrame({"ticker": [_ticker(index) for index in range(1, 50)] + ["005930"]})
        with self.assertRaises(PortfolioContractError):
            build_neutral_core_targets(core)
        spoofed = pd.DataFrame({
            "ticker": [_ticker(index) for index in range(1, 51)],
            "security_id": ["KRX_COMMON:005930"] + [f"KRX_COMMON:{_ticker(index)}" for index in range(2, 51)],
        })
        with self.assertRaises(PortfolioContractError):
            build_neutral_core_targets(spoofed)


if __name__ == "__main__":
    unittest.main()

