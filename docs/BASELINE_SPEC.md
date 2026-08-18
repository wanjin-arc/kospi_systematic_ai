# Rule Baseline Specification — Phase 3

**Version:** phase3-baseline-v1  
**Experiment:** `P3-BASELINE-20260818-001`  
**Data boundary:** development partition through 2023 only; final OOS 2024–2025 denied  
**Purpose:** a transparent, cost-aware reference rule, not a profitability claim

## 1. Signal and eligible universe

For every exchange session `t`, use only the point-in-time KOSPI 100 members that are `rank_eligible`, tradable, and eligible for a new entry at the close of `t`. No current-constituent backfill is permitted.

For stock `i`:

- `SMA200_i,t` is the mean of the last 200 session closes in the current feature-continuity segment.
- `MOM126_i,t = Close_i,t / Close_i,t-126 − 1`.
- `MOM126_K100,t = IndexClose_t / IndexClose_t-126 − 1`.
- `EXCESS126_i,t = MOM126_i,t − MOM126_K100,t`.

A stock is a candidate only when:

1. `Close_i,t > SMA200_i,t`; and
2. `EXCESS126_i,t > 0`.

Candidates are ranked by descending `EXCESS126`; exact ties use ascending `security_id`. There is no learned transform, imputation, label, rank-loss exit, discretionary chart interpretation, or random component.

## 2. Orders and holdings

- A signal is calculated after close `t` and may execute only at open `t+1`.
- Every buy carries the precommitted limit `Close_t × 1.05`; a larger opening gap cancels the order without retry.
- Compare only holding intervals `H ∈ {5, 10, 20}` and maximum holdings `N ∈ {5, 10, 15}`.
- A filled entry exits at the first tradable open after exactly `H` complete session intervals. If the security is not tradable, the exit remains due and retries at later opens.
- A fresh qualifying `t` signal may re-enter a name on the same open as its ordinary time exit. This is a new round trip and pays all costs again.
- No pyramiding, shorting, leverage, or fractional shares.
- Each entry target is `min(1/N, 10%)` of prior-close portfolio equity. Quantities round down to whole shares; cash is never forced into a weaker signal.
- Sell orders execute before buys; buy priority is rank then `security_id`.

## 3. Costs and benchmark

Every fill uses 2 bp commission per side, 10 bp adverse slippage per side, and the execution-date KOSPI statutory sell-tax schedule in `configs/kospi_sell_cost_schedule.csv`. Taxes are never removed. The primary benchmark is the KOSPI 100 price index over the identical seeded close-to-final-close period.

## 4. Corporate actions and removals

- Raw prices drive execution and cash accounting.
- Mechanical split/bonus factors create split-continuous feature prices and multiply held shares at the effective boundary.
- Phase-3 features are scale invariant. Applying a later mechanical factor to all earlier prices is mathematically identical to an explicit as-of representation for close/SMA and return ratios; an automated test verifies this equivalence.
- Rights/reorganization/reset boundaries start a new feature segment, so no 126- or 200-session lookback crosses the discontinuity.
- From the first public filing until a resolvable boundary, new entries are blocked and a known held position is scheduled for a conservative boundary-open safety exit.
- An event whose portfolio terms remain pending creates a permanent entry block from the first filing. A same-day-notice reset is accepted only when an earlier pending event already imposed that block; otherwise the run fails closed.
- Constituent removals use the supplied point-in-time removal execution date/open. Explicit successor quantity transformations use the supplied multiplier and a temporary liquidation identity to avoid merging unrelated live positions.
- Missing required factors, late unprotected notices, or failed mandatory exits invalidate the run.

## 5. Frozen selection protocol

All nine `H × N` combinations are run on Train (2011–2018) and Validation (2019–2021). Selection uses Validation only:

1. highest net zero-risk-free Sharpe;
2. higher net excess return;
3. shallower maximum drawdown;
4. lower turnover;
5. lower `H`, then lower `N`.

Only the selected combination is run on the Development Test (2022–2023), once. The reference baseline is accepted when it is deterministic, cost-aware, reconciled, and leakage tests pass. It becomes a trading candidate only if net excess return is positive in both Validation and Development Test.

## 6. Reproduction

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kospi100_baseline.cli run \
  --config configs/phase3_baseline.json \
  --output artifacts/phase3
```

The command reads only `data/processed/v24/development`. The configuration rejects sealed/final-OOS paths and dates after 2023-12-31.
