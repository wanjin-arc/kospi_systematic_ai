# Bias Prevention Checklist

**Use:** Complete and attach this checklist to every dataset release, backtest release, and model promotion. A failed or unanswered critical item blocks the result.

## 1. Point-in-Time Data (Critical)

- [ ] The universe query for every signal date returns only constituents effective at that date.
- [ ] No current constituent list has been backfilled into the past.
- [ ] Membership source, effective dates, source snapshot, and retrieval date are recorded.
- [ ] A stock cannot receive a new buy signal before its effective inclusion date or after its effective removal date.
- [ ] The trading calendar is exchange-session based and dates are sorted per symbol.
- [ ] Each OHLCV row passes `Low ≤ min(Open, Close) ≤ max(Open, Close) ≤ High` when prices are present.
- [ ] Volume and traded value are non-negative and suspicious zero/flat sequences are flagged rather than invented.
- [ ] Duplicate symbol-date bars are absent or resolved with a recorded source rule.
- [ ] Raw price data are immutable; transformed data retain vendor/source and adjustment-factor lineage.
- [ ] Split/reverse-split factors available only after the relevant effective date have not rewritten earlier as-of signals.
- [ ] Cash-dividend total-return adjustments are not being used as technical signal inputs.
- [ ] Halts, delistings, code changes, and non-tradable sessions are represented explicitly.

## 2. Signal and Feature Timing (Critical)

- [ ] Every feature lists its input fields, lookback, and latest permitted timestamp.
- [ ] A signal at `t` has no `t+1` bar, membership update, adjustment factor, or future corporate-action input.
- [ ] Cross-sectional ranks use only the eligible `U_t` population.
- [ ] Breadth uses only contemporaneous eligible constituents and has a defined treatment for halted/missing names.
- [ ] Missing values are handled by a train-fitted rule; a future cross-section/period is not used to fill them.
- [ ] Winsorisation, scaling, PCA, feature selection, thresholds, and imputation are fitted within the current training window only.
- [ ] Every feature has an automated unit test around its first valid date and lookback boundary.

## 3. Labels and Validation (Critical)

- [ ] Labels begin no earlier than the tradeable `t+1` opening point.
- [ ] The label horizon and holiday/session counting are explicit.
- [ ] Label availability is respected: observations with incomplete forward horizons are excluded from fitting/evaluation.
- [ ] Training is purged by at least the maximum forward label horizon at split boundaries.
- [ ] Embargo is applied wherever evaluated observations could later return to a training set.
- [ ] No random row-level shuffle or random train/test split is used.
- [ ] Train, validation, development test, and final OOS dates match the frozen protocol.
- [ ] Final OOS data and metrics were not accessed during feature/model/threshold selection.
- [ ] Any final-OOS inspection has a release/config/model/data hash and a permanent decision record.

## 4. Execution Simulation (Critical)

- [ ] Signal close `t` and executable open `t+1` are different sessions.
- [ ] Buy/sell fills apply adverse slippage, commissions, date-specific sale tax/surcharge, and whole-share rounding.
- [ ] The gap filter is implementable as a pre-submitted order limit; no final-open hindsight cancellation exists.
- [ ] Cash cannot go negative; rejected/unfilled orders are recorded rather than silently filled later.
- [ ] Same-day stop/target ambiguity follows the frozen conservative rule.
- [ ] Opening gaps through a stop use the opening price rather than an impossible better stop fill.
- [ ] Halts, price limits, delistings, partial fills, and suspended symbols use documented rules.
- [ ] Corporate actions update price/share/cash ledger consistently and are covered by tests.
- [ ] Portfolio valuation uses only prices available for that day and flags non-tradable stale valuations.

## 5. Experiment and Result Integrity

- [ ] Registry entry and hypothesis were created before results were reviewed.
- [ ] Dataset, source, code, configuration, and model hashes are recorded.
- [ ] Baseline comparison uses identical universe, timing, costs, and portfolio constraints.
- [ ] Gross and net results are both reported; selection is based on net results.
- [ ] Annual/fold/regime results, turnover, concentration, cash, drawdown duration, and stress costs are reported.
- [ ] Failed experiments and failed tests remain in the registry.
- [ ] No result claims use missing data, unrun code, another project's performance, or unverified broker fills.

## 6. Pre-Promotion Sign-off

| Role | Required sign-off |
|---|---|
| Data & Audit | Point-in-time universe, OHLCV, adjustment, calendar, and anomaly checks passed |
| Backtest | Synthetic execution tests passed; ledger reconciles exactly |
| Research | Hypothesis and feature cards complete; no final OOS access |
| Risk | Cost, slippage, concentration, drawdown, and kill-switch review complete |
| Release | Source/config/model/data hashes match the registered experiment |

Any unchecked critical item changes the result status to **invalid**, not merely provisional.

## Phase 3 baseline sign-off — 2026-08-18

| Critical check | Status | Evidence |
|---|---|---|
| Point-in-time members and entry eligibility | Passed | 101,734 candidates are all contemporaneous members, tradable, and `rank_eligible` |
| Split factor timing | Passed | Only scale-invariant features; future-factor/as-of equivalence unit test passes |
| Reset and unresolved corporate actions | Passed | 49 reset boundaries segmented; 29,343 entry rows blocked; late-notice event protected by prior permanent block |
| Signal/execute timing | Passed | Orders require close `t` and later session open; dedicated unit test passes |
| Selection leakage | Passed | Nine candidates selected on 2019–2021 only; one frozen candidate run on 2022–2023 |
| Final OOS access | Passed | Development-role guard; maximum loaded date 2023-12-28; access flag false |
| Costs and whole-share accounting | Passed | 2 bp commission, 10 bp adverse slippage, date-specific sell taxes; 19/19 strategy reconciliations pass |
| Experiment integrity | Passed | `P3-BASELINE-20260818-001` registered before strategy results; hashes recorded |
| Determinism | Passed | Independent repeat produced identical `manifest.json` bytes |
| Promotion gate | Failed by performance, not integrity | Reference accepted; trading candidate rejected due negative Validation and Development-Test net excess returns |

## Phase 1 actual-data audit snapshot — 2026-08-16

| Critical check | Status | Evidence / blocker |
|---|---|---|
| Historical membership changes exist instead of a current-list backfill | Passed structurally | 44 constituent-set change dates across 2010–2025; upstream provenance still unverified |
| Daily snapshots reproduce point-in-time intervals | Passed | 4,173 dates reconstructed with 0 mismatches |
| Exchange-session alignment | Partial | All 3,939 index dates have membership snapshots; official hours/early-close flags missing |
| Index OHLC/activity invariants | Passed | 0 duplicate dates, OHLC violations, non-positive prices, or negative activity rows |
| Individual-stock OHLCV invariants | Blocked | `ohlcv_raw.csv` absent |
| Stable identity/code-change handling | Blocked | Provisional display-code IDs; ISIN/code history absent |
| Corporate actions and halts | Blocked | Corporate-action and suspension files absent |
| Exactly 100 members per exchange session | Failed | 26 sessions contain 99 supplied members; no imputation performed |
| Upstream source and licence lineage | Blocked | Source screen/query/retrieval/terms not supplied |
| Final-OOS physical release | No files created | Build gate correctly refused partial/error-bearing data |
