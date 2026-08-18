# Project Charter — KOSPI 100 Technical Systematic Trading AI

**Current gate:** Phase 3 completed on 2026-08-18. Phase 4 requires explicit user approval and has not started.

**Version:** 0.3 (Phase-3 reference frozen)  
**Date:** 2026-08-18  
**Status:** Phase-3 reference accepted; its trading-candidate gate failed; Phase 4 is not authorised

## 1. Objective

Build a repeatable, daily-bar, long-only systematic trading system for the KOSPI 100. The objective is not to maximise an in-sample return. It is to determine, through point-in-time data, cost-aware testing, walk-forward validation, paper trading, and small-scale live operation, whether a technically driven process is sufficiently robust to operate.

The production path is:

`Point-in-time OHLCV → technical features → cross-sectional ranking → entry timing → regime/risk control → portfolio/execution → backtest → walk-forward → 5,000,000 KRW paper trading → small live trading`

## 2. Fixed Scope

| Area | Rule |
|---|---|
| Universe | KOSPI 100, using the constituents actually effective at each historical date |
| Instruments | Korean listed common shares eligible in the universe; long-only, cash equities |
| Exclusions | Shorting, leverage, margin, derivatives, fundamental data, DART, news, text, analyst views, sector judgement |
| Signal inputs | OHLCV, traded value, KOSPI 100 index prices, and breadth calculated only from the contemporaneous universe |
| Frequency | Daily bars for the initial system |
| Information timing | Compute after the close of day `t` from information available by that close; submit/execute no earlier than day `t+1` |
| Portfolio | May hold cash; it is not required to be fully invested |
| Initial paper capital | KRW 5,000,000 |

All symbols use the same feature definitions and rules. Corporate-action, code-change, halt, and calendar data may be used only to make data and execution valid; they are never predictive factors.

## 3. System Boundaries

The initial implementation has five components:

1. **Data & Audit** — point-in-time universe, OHLCV, calendars, data lineage, and automated quality checks.
2. **Technical Cross-sectional Ranker (Agent B)** — a daily, same-universe ranking derived only from technical variables.
3. **Entry Timing Gate (Agent C)** — an implementable decision on whether a ranked candidate may be entered.
4. **Market Regime & Risk Controller** — KOSPI 100 price and contemporaneous breadth only; it can reduce long exposure or hold cash but never short.
5. **Portfolio, Execution & Monitoring** — position sizing, orders, fills, reconciliation, audit logs, and kill switches.

AI may propose hypotheses and feature cards. No subjective chart reading, uncomputed narrative, or opaque discretionary override can create a trade.

## 4. Research Dataset and Sealed Evaluation Policy

The intended research window is **2011-01-01 through 2025-12-31**. Stage 1 must confirm the first and last actual exchange sessions and the availability of a point-in-time KOSPI 100 universe. The research window must not be silently shortened: a failure to obtain an auditable universe or price history is a logged blocker requiring approval.

| Partition | Calendar period | Permitted use |
|---|---:|---|
| Initial train | 2011–2018 | Fit initial transforms/models and formulate candidate rules |
| Initial validation | 2019–2021 | Select among pre-declared variants and reject weak ideas |
| Development test | 2022–2023 | One limited confirmation after a version is frozen |
| Final out-of-sample (OOS) | 2024–2025 | Sealed until Phase 8 only |
| Post-cutoff live shadow period | 2026 onward | Paper/live operational evidence, never retrospective model selection |

The final OOS files must be access-controlled or stored separately, listed in a sealed manifest, and blocked from ordinary experiment pipelines. Its metrics may be calculated once for a frozen release in Phase 8. If they are used to change features, thresholds, targets, costs, or portfolio rules, that OOS result is invalidated permanently and a new later untouched period is required.

## 5. Governance

- Every consequential design choice is recorded as a decision with date, owner, status, and reason.
- Every strategy or model run has an immutable experiment ID and a row in `experiments/registry.csv` before its result is reviewed.
- Training-only operations include fitting scalers, winsorisation limits, imputers, feature selection, thresholds, and model hyperparameters.
- Random time-series train/test splitting is forbidden.
- A failed data, bias, or execution test blocks promotion regardless of reported return.
- This charter can change only through a new decision-log entry and explicit user approval. A change that touches the sealed OOS policy requires a new OOS period.

## 6. Stage Gates and Completion Conditions

| Phase | Completion condition | Approval gate |
|---|---|---|
| 0. Research rules | Charter, protocol, bias checklist, decision log, registry schema completed and reviewed | User approval required before Phase 1 |
| 1. Point-in-time data | Date-specific universe and history-only OHLCV are queryable; data tests, lineage, and quality report pass | Completed and approved; v24 PASS |
| 2. Backtest engine | Deterministic ledger and performance output; all specified synthetic execution cases pass | Completed; user approval required before Phase 3 |
| 3. Rule baseline | Completed: reproducible reference accepted; trading-candidate gate failed | User approval required before Phase 4 |
| 4. Feature research | Each proposed feature has a feature card and a recorded accept/reject decision without opening final OOS | User approval required before Phase 5 |
| 5. Ranking model | Candidate improves on the baseline under the pre-committed development criteria, or is explicitly rejected | User approval required before Phase 6 |
| 6. Timing model | Candidate improves risk-adjusted, net-of-cost portfolio results versus Agent B alone, or is rejected | User approval required before Phase 7 |
| 7. Portfolio/risk | Exposure, regime rules, stress tests, reconciliation, and kill switches are defined and tested | User approval required before Phase 8 |
| 8. Integrated robustness | Walk-forward, stress, sensitivity, and one-time final OOS review complete with a risk review | User approval required before Phase 9 |
| 9. Paper trading | Realistic account simulation, reconciliation, order/error logging, and sufficient representative cases complete | User approval required before Phase 10 |
| 10. Small live trading | Entry checklist, version hash, operational controls, and bounded capital plan approved | Separate explicit approval required |

## 7. Non-Goals Before Validation

No intraday model, deep-learning model, multi-agent service, cloud redundancy, dashboard, automated brokerage order, or market expansion is in scope until the daily KOSPI 100 system has passed its relevant stage gate.

## 8. Phase-0 Outstanding Items

These matters are intentionally not guessed and are resolved at the stated point:

| Item | Why unresolved | Resolution point |
|---|---|---|
| Auditable historical constituent source | Coverage, effective-date fields, and licence must be inspected | Phase 1 before collecting model data |
| Vendor and API selection | Depends on the available source's point-in-time coverage and adjustment metadata | Phase 1 |
| Exact historical sell-tax calendar | Verified and implemented for 2011–2025; see `configs/kospi_sell_cost_schedule.csv` | Resolved in Phase 2 |
| Actual broker commission and order semantics | Account and broker are not selected | Before Phase 9; use conservative research proxy until then |
| Price-limit, halt, and auction fill metadata | Depends on the data/vendor and broker execution specification | Phase 1–2 |
| Live capital amount and broker API | Requires a completed risk review and separate authorization | Phase 10 only |
