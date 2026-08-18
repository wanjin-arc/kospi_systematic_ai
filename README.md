# KOSPI 100 Technical Systematic Trading AI

Current gate: **Phase 3 complete; Phase 4 has not started and requires explicit user approval.**

Phase 1 v24 provides audited point-in-time daily data through 2025-12-30, with development rows physically separated through 2023-12-31 and final OOS 2024–2025 sealed. Phase 2 adds a deterministic long-only daily execution/accounting engine. Phase 3 freezes and evaluates a transparent dual-momentum rule baseline. The reference is reproducible but failed the trading-candidate excess-return gate. There is no ML ranking model, timing model, or brokerage integration.

## Implemented

- Point-in-time KOSPI 100 memberships, stock/index daily OHLCV, corporate-action controls, and intraday coverage audit.
- Ordinary development access refuses final-OOS dates.
- Frozen-order daily backtest engine with whole shares, cash limits, gaps, halts, partial fills, costs, stops/targets, and corporate actions.
- Cash, position, fill, equity, trade, audit, metric, and reconciliation outputs.
- Deterministic hashes and byte-identical artifact serialization.
- Phase-3 close/SMA200 plus 126-session excess-momentum rank, evaluated across only nine predeclared `H × N` combinations.
- Validation-only selection of `H=20, N=10`; reference accepted, trading candidate rejected.

Specifications and gate evidence:

- `docs/DATA_SPEC.md`
- `docs/BACKTEST_SPEC.md`
- `docs/PHASE2_VALIDATION_REPORT.md`
- `docs/BASELINE_SPEC.md`
- `docs/PHASE3_VALIDATION_REPORT.md`
- `data/quality/v24/phase1_v24_independent_audit.json`

## Verify

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kospi100_backtest.demo \
  --output artifacts/phase2/synthetic_reference
PYTHONPATH=src python -m kospi100_baseline.cli run \
  --config configs/phase3_baseline.json \
  --output artifacts/phase3
```

The test suite uses synthetic execution data. Synthetic performance is a calculation check, not a strategy result. The Phase-2 demo does not open the sealed final OOS.

## Key directories

- `src/kospi100_data/`: Phase-1 audit, partition, and guarded access.
- `src/kospi100_backtest/`: Phase-2 engine, costs, metrics, and deterministic writers.
- `src/kospi100_baseline/`: Phase-3 data guard, features, rule orders, selection, and reporting.
- `configs/`: frozen engine and KOSPI sell-cost schedules.
- `artifacts/phase2/synthetic_reference/`: reference ledgers and performance output.
- `artifacts/phase3/`: Phase-3 sensitivity, selected-period ledgers, metrics, and manifests.
- `data/processed/v24/development/`: development-only daily data through 2023.
- `data/sealed/final_oos_v24/`: Phase-8-only final OOS; do not use for development.
