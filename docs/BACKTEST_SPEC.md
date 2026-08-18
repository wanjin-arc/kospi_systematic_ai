# Backtest Specification — Phase 2

**Version:** phase2-engine-v1  
**Scope:** deterministic long-only daily execution and accounting only  
**Data boundary:** development data through 2023-12-31; final OOS 2024–2025 remains sealed

## 1. Purpose and boundary

The engine accepts a session calendar, daily bars, pre-frozen orders, corporate-action events, and optional benchmark closes. It produces orders, fills, cash and position ledgers, daily equity, closed trades, metrics, audit events, hashes, and a reconciliation report.

It does **not** create technical features, ranks, entry signals, labels, portfolio-selection rules, or ML models. Those belong to later phases. This separation ensures that execution code cannot inspect a future bar to decide whether an order should have existed.

## 2. Information and event order

For a signal observed after close on session `t`:

1. the order is frozen with `signal_date=t`;
2. `execute_date` must be a later listed session;
3. corporate actions effective on the execution session are applied before the open;
4. sells execute before buys so released cash is available deterministically;
5. sells and buys are ordered by `(priority, security_id, order_id)`;
6. opening orders use that session's raw open as the reference price;
7. intraday stop/target rules are evaluated after opening orders;
8. positions are marked at current valid close, or at the last valid close with a stale flag;
9. cash, positions, and equity are reconciled at the session close.

An order with `signal_date >= execute_date`, a duplicate order ID, a duplicate bar, or a date outside the supplied exchange calendar is rejected before simulation.

## 3. Fill rules

### Entries

- Long-only and whole shares only.
- A buy specifies exactly one of an exact quantity, cash budget, or target weight.
- Cash-affordable quantity includes the buy commission and is rounded down.
- Pyramiding is disabled for the Phase-2 baseline.
- An optional maximum-position count rejects excess entries deterministically.
- A predeclared maximum holding interval creates an ordinary open exit after the exact number of session intervals; blocked exits remain due.
- A precommitted buy limit implements the opening-gap cap. If raw open exceeds it, the order is not filled.
- Buy fill price is `raw reference × (1 + buy slippage)`.
- A missing or non-tradable bar produces no fill.
- An explicit synthetic/data-supplied liquidity cap may produce a partial fill. The unfilled day-order remainder is cancelled.

### Exits

- Scheduled sells cannot exceed the current long position; an excess request is rejected rather than creating a short.
- Sell fill price is `raw reference × (1 − sell slippage)`.
- Commission, securities transaction tax, and rural special tax are deducted from proceeds.
- A partial sell retains the remaining cost basis pro rata and cancels the day-order remainder.

### Stops and targets

- Opening below the stop: use the adverse opening price.
- Both stop and target reachable in one daily bar: stop first.
- Stop only: use the stop reference price.
- Target only, including a gap above target: use no better than the target reference price.
- Adverse sell slippage applies to the selected reference price.

This daily rule is deliberately conservative and is not reused silently when minute-bar sequencing becomes available.

## 4. Costs

Research defaults are 2 bp commission per side and 10 bp adverse slippage per side. Monetary charges are calculated with `Decimal` and rounded down to one KRW. Broker-specific fee rounding remains a Phase-9 verification item.

The KOSPI sell schedule is versioned in `configs/kospi_sell_cost_schedule.csv`:

| Execution dates | Securities transaction tax | Rural special tax | Total |
|---|---:|---:|---:|
| 2011-01-01–2019-06-02 | 0.15% | 0.15% | 0.30% |
| 2019-06-03–2020-12-31 | 0.10% | 0.15% | 0.25% |
| 2021-01-01–2022-12-31 | 0.08% | 0.15% | 0.23% |
| 2023-01-01–2023-12-31 | 0.05% | 0.15% | 0.20% |
| 2024-01-01–2024-12-31 | 0.03% | 0.15% | 0.18% |
| 2025-01-01–2025-12-31 | 0.00% | 0.15% | 0.15% |

Primary legal basis: the National Law Information Center's [Securities Transaction Tax Act Enforcement Decree amendment history](https://law.go.kr/LSW/lsRvsDocListP.do?chrClsCd=010202&lsId=005028&lsRvsGubun=all) and [Rural Special Tax Act Article 5](https://law.go.kr/LSW//lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1031850597). An execution date outside the verified schedule fails rather than silently reusing the last rate.

## 5. Corporate actions

- Split and bonus issue: multiply shares by the supplied factor without changing retained total cost basis.
- Fractional result: require a cash-in-lieu price; otherwise fail closed.
- Successor/reorganization: transform identity and quantity only with an explicit successor and multiplier.
- Cash component: post separately to the cash ledger and attribute removed cost basis.
- Pending rights, bonus, merger, or other economic terms encountered while a position is held: stop the run with `UnresolvedCorporateActionError`.

The engine never guesses an entitlement or successor ratio. This is important because the Phase-1 v24 action table intentionally retains events whose portfolio terms still require verification.

## 6. Accounting and reconciliation

The following identities must all pass:

- `final cash = sum(all cash-ledger entries)`, including initial capital exactly once;
- every buy cash delta equals `−(gross notional + commission)`;
- every sell cash delta equals `gross − commission − transaction tax − rural tax`;
- final position quantity equals the sum of all position-ledger deltas;
- every final quantity is non-negative;
- final equity equals `cash + marked position value`;
- cash never becomes negative.

Cost basis uses average/pro-rata allocation for partial exits. A closed trade records net realized P&L, net return, and holding sessions. All IDs and processing orders are deterministic.

## 7. Performance output

The engine reports total return, CAGR, annualized volatility, zero-risk-free Sharpe, zero-target Sortino, MDD, drawdown duration, Calmar, benchmark return and annualized alpha when supplied, annual returns, win rate, average win/loss, payoff, turnover, costs, slippage, holding period, cash weight, stale marks, and order-status counts.

These metrics validate the engine output contract. The synthetic reference result is not evidence of a profitable strategy.

## 8. Deterministic artifacts

`python -m kospi100_backtest.demo --output <directory>` writes:

- `fills.csv`
- `order_events.csv`
- `cash_ledger.csv`
- `position_ledger.csv`
- `position_snapshots.csv`
- `equity_curve.csv`
- `closed_trades.csv`
- `audit_events.csv`
- `metrics.json`
- `reconciliation.json`
- `run.json`
- `manifest.json`

The input hash is independent of input iteration order. The same logical input and configuration must produce byte-identical artifacts.

## 9. Explicit limitations

- Daily OHLC does not prove auction availability or intraday price order.
- The v24 daily data does not provide historical order-book depth, exact partial-fill quantities, or complete price-limit/auction flags. Full fills are therefore the research default unless an explicit cap/status is supplied.
- Stale marking during a halt preserves accounting continuity but is not a claim that the position could be liquidated.
- Actual broker commission, tick rounding, marketable-limit semantics, rejection codes, and order states remain for paper-trading integration.
- No final-OOS data was opened in Phase 2.
