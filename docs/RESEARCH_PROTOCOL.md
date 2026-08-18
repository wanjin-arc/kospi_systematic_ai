# Research Protocol — Phase 0

**Applies to:** KOSPI 100 daily technical system  
**Version:** 0.1  
**Decision authority:** Changes require an approved entry in `docs/DECISION_LOG.md`.

## A. Global Conventions

- `t` is an exchange trading day. All features at `t` use only data available after the official close of `t`.
- A daily signal is frozen before the next trading session. It may be executed only on `t+1` or later.
- `U_t` is the KOSPI 100 constituent set effective at the close of `t`, reconstructed point-in-time. A candidate must be in `U_t` to be ranked or newly bought.
- The primary initial model clock is **signal close `t` → entry open `t+1` → exit open**. A return label therefore measures a return that could actually follow a signal.
- All dates below are calendar boundaries. Phase 1 replaces them with the corresponding confirmed exchange sessions without changing the partition intent.

## B. Decisions

### D01. Research start and end dates

- **Recommendation:** Use the pre-committed data window 2011-01-01 to 2025-12-31, conditional on Phase 1 finding an auditable point-in-time universe and usable daily data throughout. Do not include 2026 in model development.
- **Reason:** Fifteen calendar years provide several different Korean market regimes while leaving 2024–2025 as a meaningful sealed period. Keeping 2026 outside retrospective development preserves a current paper/live shadow period.
- **Important alternative:** Start later only if audited data cannot support 2011. This is a material protocol change, not a convenience change.
- **Impact:** A missing historical universe can block the project; it must not be replaced by today's constituent list.
- **Status:** Confirmed as the target window; data availability is pending Phase 1.

### D02. Historical KOSPI 100 constituents

- **Recommendation:** Store a versioned membership table with `symbol_id`, display code, effective start/end date, announcement date/time where available, source, and source snapshot. Use only `U_t` for features, ranks, breadth, and new entries at `t`.
- **Reason:** This prevents survivorship bias and makes a past date query reproducible.
- **Important alternative:** Use current constituents over the entire period. It is rejected because it creates survivorship bias.
- **Impact:** Constituents added on `t+1` cannot be bought from a signal at `t`; a removed stock cannot receive a new buy order. An existing removed position is handled by the pre-declared exit rule in D06/D13.
- **Status:** Confirmed; source and effective-date validation are pending Phase 1.

### D03. Raw and adjusted prices

- **Recommendation:** Retain immutable vendor raw OHLCV. Generate a separate **as-of-date, split/reverse-split-adjusted** OHLCV series for technical features. Do not use a retrospectively dividend-adjusted total-return series for signals. Execute and account for cash using raw tradable prices, share quantities, and corporate-action events.
- **Reason:** Split adjustments preserve chart continuity without allowing a later corporate action to rewrite what was knowable at `t`. Cash dividends are not an approved information input and should not be converted into a predictive total-return signal.
- **Important alternative:** Use a vendor's fully back-adjusted close series. It is acceptable only for a separately labelled reporting series, never for signal calculations unless the vendor can provide an as-of history.
- **Impact:** Phase 1 must retain adjustment factor lineage and test split dates; Phase 2 must apply position/share adjustments to its ledger.
- **Status:** Confirmed, subject to data-source capability verification.

### D04. Signal calculation time

- **Recommendation:** Calculate all end-of-day signals after the official close of `t`, using bars, membership, and corporate-action knowledge effective no later than that close. Freeze the signal and its inputs before `t+1`.
- **Reason:** This is directly implementable in an end-of-day process and rules out same-bar execution.
- **Important alternative:** Intraday signals. Deferred; they need independent data and execution validation.
- **Impact:** No feature, rank, threshold, or standardisation parameter may consume `t+1` data.
- **Status:** Confirmed.

### D05. Order execution time

- **Recommendation:** The base simulation submits an order from the frozen `t` signal for the opening auction/session on `t+1`. The default entry and ordinary exit fill is `Open[t+1]` adjusted adversely by the configured slippage model.
- **Reason:** It enforces a full trading-day separation between observation and execution.
- **Important alternative:** Same-day close execution. Rejected because the official close is not known before that fill.
- **Impact:** Feature labels and the engine must use open-to-open tradable return timing.
- **Status:** Confirmed.

### D06. Next-open gaps and opening fills

- **Recommendation:** New buys use a pre-submitted marketable limit: `max_buy_price = Close[t] × (1 + g_max)`, with initial `g_max = 5%`. If the `t+1` opening price exceeds the cap, record an unfilled entry; do not replace it at a later favourable price. Risk exits are not cancelled by this entry filter. Filled buys use `Open[t+1] × (1 + slippage_buy)` and sells use `Open[t+1] × (1 - slippage_sell)`.
- **Reason:** A known opening price cannot be used after the fact to decide whether to buy. A pre-set limit models an implementable gap guard.
- **Important alternative:** Always fill at next open, with no gap filter. It remains a required sensitivity run. A rule that observes the final open and then retroactively cancels is rejected.
- **Impact:** The gap cap is a train/validation-selected candidate parameter, not an OOS-tuned one. Unfilled signals remain logged.
- **Status:** Confirmed as the base execution convention; exact broker order support is pending Phase 9.

### D07. Same-day stop and target contact

- **Recommendation:** Use a conservative OHLC rule. If the opening price is beyond a stop, sell at the adverse opening fill. If both a stop and target are reachable after an entry/while held within the same daily bar and the intraday order is unknowable, treat the **stop as reached first**. If only the target is reached, fill no better than the target price; if only the stop is reached, fill at the stop price, subject to an adverse opening gap.
- **Reason:** Daily OHLC does not reveal high/low order. Selecting the target first would create optimistic bias.
- **Important alternative:** Ignore same-day protective exits. This loses realism and remains only a diagnostic comparison.
- **Impact:** The engine must label this execution assumption in every run; a later intraday system cannot reuse this assumption silently.
- **Status:** Confirmed.

### D08. Initial holding-period candidates

- **Recommendation:** Compare holding horizons of **5, 10, and 20 trading sessions**, plus a rank-loss exit if its definition is pre-declared. Use 10 sessions only as the initial baseline, not as an assumed optimum.
- **Reason:** The range covers short swing and medium momentum without introducing an uncontrolled parameter search.
- **Important alternative:** Fix 10 days because another project used it. Rejected.
- **Impact:** Horizon selection occurs only on training/validation; development test and final OOS use the frozen selected horizon.
- **Status:** Phase-3 reference selected 20 sessions by Validation-only net Sharpe. Later model stages may supersede it only through their own predeclared gate.

### D09. Agent B ranking targets

- **Recommendation:** Make the primary ranking target the cross-sectional rank of 10-session, KOSPI 100 price-index excess return: `r_i = log(Open[i,t+11] / Open[i,t+1]) - log(IndexOpen[t+11] / IndexOpen[t+1])`, calculated within eligible `U_t`. Compare 5- and 20-session versions and a volatility-adjusted excess-return target only as pre-declared candidates.
- **Reason:** It measures the return that follows a tradeable next-open signal and directly matches the relative-ranking objective.
- **Important alternative:** Raw forward return. It is a valid comparator but can unintentionally reward market beta.
- **Impact:** Labels overlap; D18 purge/embargo rules are mandatory. Ranking metrics never replace cost-aware portfolio evaluation.
- **Status:** Confirmed primary target and limited candidate family.

### D10. Agent C timing labels

- **Recommendation:** Start with two labels, evaluated separately: (1) a 10-session triple-barrier label where `+2 × ATR20[t]` is hit before `−1 × ATR20[t]`; ties/unknown daily-bar ordering are negative; (2) a 10-session forward excess-return label above the 60th percentile within Agent B's eligible candidate set. The selected threshold must be fitted only in train windows.
- **Reason:** The first tests tradable risk/reward sequencing, while the second tests continuation without assuming a particular stop/target structure is universally correct.
- **Important alternative:** CNN/LSTM image labels. Deferred until simple rules and tabular models show a stable gap.
- **Impact:** Neither label may use an intraday ordering not present in daily data. Class balance and probability calibration are required in Phase 6.
- **Status:** Confirmed candidate labels; no model or winner chosen.

### D11. Benchmark

- **Recommendation:** Use the KOSPI 100 **price index**, matching the research period and daily price convention, as the primary performance benchmark. Compare returns over the same entry/exit dates; report its buy-and-hold price return separately from a cash-aware strategy.
- **Reason:** It represents the assigned universe without importing dividend or fundamental assumptions that are outside the signal scope.
- **Important alternative:** KOSPI composite or a total-return index. They may be supplementary context only and cannot replace the primary benchmark.
- **Impact:** Benchmark OHLC and index methodology/lineage must be included in the data dictionary.
- **Status:** Confirmed; vendor identification is pending Phase 1.

### D12. Commissions, taxes, and slippage

- **Recommendation:** Use a versioned, calendar-date cost schedule. Until an actual broker is selected, the base research proxy is **2 bps commission per side**, the legally applicable KOSPI sale tax/surcharge by each execution date, and **10 bps adverse slippage per side**. Required stress runs are 2× and 3× slippage and commission; tax is never removed.
- **Reason:** Costs are strategy-sensitive and tax rates vary by date. A conservative configurable proxy avoids hard-coding an unverified current brokerage price.
- **Important alternative:** Apply one flat round-trip fee for all history. Rejected for the production evaluation, but can be a clearly marked diagnostic only.
- **Impact:** Phase 1 must verify and version the historical statutory sell-cost table from authoritative sources. Phase 9 replaces the commission proxy with the selected broker's actual schedule before any order is placed.
- **Status:** Historical 2011–2025 statutory schedule implemented in Phase 2; broker-specific fee and rounding remain pending until Phase 9.

### D13. Maximum holdings

- **Recommendation:** Use 10 equal-capacity slots for the initial baseline and compare only `N ∈ {5, 10, 15}` in train/validation. Allow fewer positions and retain cash when fewer valid signals exist.
- **Reason:** Ten names provides diversification while retaining a meaningful rank selection in a 100-name universe.
- **Important alternative:** Always fully invest in the top 100. Rejected because the system is intended to be selective and cash is an explicit risk control.
- **Impact:** `N` is frozen before development test/OOS. A constituent removal does not create a replacement purchase unless the ordinary next signal permits one.
- **Status:** Phase-3 reference selected 10 holdings by Validation-only net Sharpe. Later portfolio research remains gated.

### D14. Initial position sizing

- **Recommendation:** Use equal target notional weights: `min(1/N_selected, 10%)` per filled position, rounded down to whole shares. Unallocated cash remains cash. No volatility scaling, pyramiding, or leverage in the baseline.
- **Reason:** Equal weights are transparent, deterministic, and avoid early dependence on noisy volatility estimates.
- **Important alternative:** Inverse-volatility weights. Defer to Phase 7 and accept only if it improves net robustness.
- **Impact:** Fees are deducted before sizing final quantities; insufficient cash results in deterministic priority by rank and then symbol ID.
- **Status:** Confirmed for baseline.

### D15. Train, validation, development test, and final OOS split

- **Recommendation:** Use 2011–2018 train, 2019–2021 validation, 2022–2023 development test, and sealed 2024–2025 final OOS. Do not randomise rows or dates.
- **Reason:** This preserves time order and reserves two complete recent years that are not touched by model design.
- **Important alternative:** A single train/test split. Rejected because it confuses model selection with final evaluation.
- **Impact:** Preprocessing is fitted in the current training portion only. Any post-2023 development decision cannot inspect final OOS metrics.
- **Status:** Confirmed conditional on D01 data availability.

### D16. Walk-forward method

- **Recommendation:** Use an anchored annual walk-forward within 2011–2023: initial training ends in 2018, validate 2019; then expand through each completed year and validate the next year through 2023. Refit all learned transforms and models at every fold. Report fold metrics separately and aggregated.
- **Reason:** Anchoring uses limited data efficiently and exposes temporal instability rather than averaging it away.
- **Important alternative:** Rolling five-year windows. It is a required robustness comparison in Phase 8, not the base development protocol.
- **Impact:** The 2024–2025 final OOS is excluded from all folds, tuning, and feature selection.
- **Status:** Confirmed; annual walk-forward execution remains scheduled for Phase 8.

### D17. Final OOS protection

- **Recommendation:** Maintain a sealed manifest of final-OOS datasets and deny ordinary experiment jobs read access to 2024–2025. At Phase 8, evaluate one release candidate with a recorded Git/source hash, config hash, model hash, and frozen registry entry. Read the result once.
- **Reason:** A repeatedly observed test set becomes a validation set.
- **Important alternative:** Run OOS after every feature idea. Rejected.
- **Impact:** Any change after the OOS report invalidates it. The next decision must use paper data or a new untouched later OOS period.
- **Status:** Confirmed; technical access control is deferred until Phase 1 repository setup.

### D18. Purge and embargo

- **Recommendation:** Apply purge and embargo in all label-based validation. With the maximum declared horizon of 20 sessions, remove the last 20 labelled sessions before each validation/test boundary from training and embargo the first 20 sessions after an evaluation block before those rows can re-enter later training. In strictly forward-only folds the embargo may be vacuous, but it remains encoded and tested.
- **Reason:** Forward labels overlap future returns across split boundaries even when rows are chronologically ordered.
- **Important alternative:** No purge because daily labels appear independent. Rejected.
- **Impact:** Effective training sample size is lower but label leakage risk is materially reduced. If a longer label is approved, this window must increase first.
- **Status:** Confirmed; not applicable to the label-free Phase-3 rule baseline.

### D19. Baseline adoption

- **Recommendation:** A rule-based baseline is accepted as the project reference only when it has deterministic rules, passing data/bias/engine tests, complete ledger outputs, and cost/slippage included. It is a *trading candidate* only if the aggregated validation and development-test results show positive net excess return versus the benchmark, no failed fold caused by a data issue, and no final-OOS access.
- **Reason:** A reproducible baseline is needed even if it proves unprofitable; it is the honest comparison point for later complexity.
- **Important alternative:** Reject every baseline below a high return target. Rejected because it would encourage hidden tuning before a proper reference exists.
- **Impact:** Phase 3 can conclude that no viable baseline exists. That is a valid outcome and blocks claims of model improvement.
- **Status:** Implemented in Phase 3: the reference was accepted, but the trading-candidate gate failed because Validation and Development-Test net excess returns were negative.

### D20. ML model adoption

- **Recommendation:** Adopt a non-baseline model only if, versus the frozen baseline on identical universe, execution, and costs: (a) all data/bias tests pass; (b) at least 80% of annual walk-forward validation folds have non-negative net excess return; (c) aggregated validation net Sharpe improves by at least 0.10; (d) development-test net excess return is positive and exceeds the baseline; and (e) development-test MDD is not worse by more than `max(5 percentage points, 20% of baseline MDD)`. All conditions must also hold under 2× transaction-cost stress, except the Sharpe-improvement threshold may be zero under stress.
- **Reason:** A higher backtest return alone is not a sufficient reason to add model complexity.
- **Important alternative:** Select by AUC, NDCG, or rank IC alone. Rejected; they remain diagnostic metrics.
- **Impact:** Failure to meet any condition means retain the simpler model. Final OOS is not used to choose a model.
- **Status:** Confirmed; Phase 5 may refine only non-material implementation details.

### D21. Experiment records

- **Recommendation:** Create the registry row before reviewing results. Use a monotonic ID `EXP-YYYYMMDD-###`, immutable result fields, a source/config/data hash, and links to generated artefacts. Superseding an experiment creates a new row; it never overwrites the old result.
- **Reason:** This prevents result-driven rewriting of hypotheses and preserves reproducibility.
- **Important alternative:** Free-form notes only. Rejected.
- **Impact:** An experiment without a completed registry row is not evidence for model selection.
- **Status:** Confirmed; schema is in `experiments/registry.csv`.

### D22. Paper-trading entry

- **Recommendation:** Enter KRW 5,000,000 paper trading only after Phase 8 approval, a frozen release/config hash, deterministic order generation, reconciliation checks, and a verified broker/API simulation path. Completion requires at least 60 market sessions **and** 30 completed position exits, plus representative tests/logs for normal fills, unfilled orders, partial fills if supported, halts, stale data, API failure, restart, and duplicate-order prevention.
- **Reason:** Duration alone does not validate an order system; a return backtest cannot verify operational correctness.
- **Important alternative:** Start paper trading as soon as a backtest is positive. Rejected.
- **Impact:** If signal frequency is too low to produce the required cases, extend paper trading rather than change the strategy merely to create trades.
- **Status:** Confirmed; selected broker/API is pending.

### D23. Small live-trading entry

- **Recommendation:** Require final-OOS and robustness approval, paper-trading completion, at least 90 market sessions and 50 completed paper exits, no unreconciled order/ledger discrepancy, tested kill switches, fixed source/config/model hashes, and explicit separate approval of an affordable live capital limit. The first live release uses the identical approved rules; no discretionary selection of signals.
- **Reason:** Live operation adds execution and operational risks not observable in historical data.
- **Important alternative:** Move to live trading after a short successful paper period. Rejected.
- **Impact:** Capital sizing, broker credentials, and order authority remain outside this research protocol until this gate is satisfied.
- **Status:** Confirmed; no live-trading authority is granted by this document.

### D24. Kill switches

- **Recommendation:** Implement two levels. **Hard operational stop:** immediately cancel pending entries and block new entries on duplicate-order detection, unreconciled cash/position state, missing/stale required data, failed universe/timestamp validation, model/config/hash mismatch, broker/API authentication or response uncertainty, or a breached position/cash limit. **Risk stop:** block new entries and maintain only protective exits when daily net liquidation loss reaches 3% or peak-to-trough portfolio drawdown reaches 12%, pending review. Any hard stop requires manual reconciliation and an explicit restart record.
- **Reason:** A system must fail safely before it fails profitably or unprofitably.
- **Important alternative:** A return-only stop. Rejected because operational errors can be more dangerous than a normal market loss.
- **Impact:** Exact broker cancel/liquidation behaviour is tested in Phase 9; no automatic forced liquidation is assumed when the broker state itself is uncertain.
- **Status:** Confirmed as initial thresholds; Phase 7 may tighten but not relax them without approval.

## C. Feature-Card Requirement

Every new technical feature has a dated card containing: formula; data fields; as-of calculation time; lookbacks; expected sign; rationale; failure regimes; correlation/redundancy with existing features; missingness; leakage analysis; unit test; train-only validation design; adoption threshold; and decision. A feature may not enter a model solely because it looks persuasive on a chart.

## D. Unresolved Items and Decision Timing

| Item | Decision timing | Blocker if unresolved |
|---|---|---|
| Historical constituent data source and licensing | Phase 1 start | Blocks model dataset creation |
| Exact sessions/calendar and valid first history date | Phase 1 audit | Blocks partition finalisation |
| Historical tax-rate table | Resolved in Phase 2 from National Law Information Center statutory history | No longer open |
| Broker, commission schedule, marketable-limit semantics | Before Phase 9 | Blocks paper/live order implementation |
| Price limits, halts, auction and partial-fill metadata | Phase 1–2 | Blocks production execution claims |
| Exact rank-loss exit definition | Resolved in Phase 3: excluded from the reference baseline | No longer open for the frozen baseline |
| Model family and feature set | Phases 4–6 | Must not be decided in Phase 0 |
