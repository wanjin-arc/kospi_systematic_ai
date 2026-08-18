# Phase 3 Validation Report

**Experiment:** `P3-BASELINE-20260818-001`  
**Run date:** 2026-08-18 KST  
**Outcome:** reference baseline **ACCEPTED**; trading candidate **FAIL**  
**Next gate:** Phase 4 not started; explicit user approval required

## Executive result

The pre-registered Validation objective selected `H=20` sessions and `N=10` holdings, with a 10% target weight per entry. The rule is deterministic, cost-aware, point-in-time, exactly reconciled, and independently reproduced byte-for-byte. It is therefore accepted as the project's honest rule reference.

It is not a trading candidate. Validation net excess return was −61.82 percentage points and Development-Test net excess return was −1.12 percentage points. Both had to be positive under the frozen D19 gate.

| Period | Strategy return | KOSPI 100 | Net excess | Sharpe | MDD | Explicit costs | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| Train 2011–2018 | −55.76% | −2.66% | −53.10 pp | −0.492 | −66.49% | ₩1,553,918 | 964 |
| Validation 2019–2021 | −11.43% | +50.40% | −61.82 pp | −0.101 | −40.55% | ₩694,919 | 360 |
| Development Test 2022–2023 | −10.35% | −9.23% | −1.12 pp | −0.179 | −28.67% | ₩457,413 | 240 |

Returns and costs are net of 2 bp commission per side, 10 bp adverse slippage per side, and date-specific statutory sell taxes. “Net excess” is arithmetic strategy return minus the KOSPI 100 price-index return over the identical period.

## Validation-only sensitivity and selection

The Development Test was not used in this table or in selection.

| H | N | Validation return | Net excess | Sharpe | MDD | Turnover |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 5 | −33.24% | −83.63 pp | −1.184 | −34.86% | 116.69× |
| 5 | 10 | −45.86% | −96.26 pp | −1.051 | −48.75% | 229.96× |
| 5 | 15 | −44.58% | −94.98 pp | −1.312 | −45.22% | 209.20× |
| 10 | 5 | −24.54% | −74.94 pp | −0.763 | −34.01% | 61.46× |
| 10 | 10 | −23.75% | −74.15 pp | −0.343 | −46.33% | 124.70× |
| 10 | 15 | −27.70% | −78.10 pp | −0.619 | −37.77% | 114.30× |
| 20 | 5 | −17.29% | −67.69 pp | −0.494 | −27.95% | 31.35× |
| **20** | **10** | **−11.43%** | **−61.82 pp** | **−0.101** | **−40.55%** | **63.61×** |
| 20 | 15 | −15.33% | −65.73 pp | −0.245 | −37.40% | 59.79× |

All nine variants lost money net in Validation and lagged the benchmark. `H=20, N=10` was selected solely because it had the highest predeclared net Sharpe; the selection does not imply profitability.

## Integrity evidence

| Check | Result |
|---|---|
| Registry entry created before result review | PASS |
| Development-role manifest hashes | 6/6 verified |
| Maximum loaded market date | 2023-12-28 |
| Final OOS accessed | No |
| Point-in-time/rank-eligible candidate invariant | PASS |
| Mechanical-action scale-invariance test | PASS |
| Reset segment and entry-blackout test | PASS |
| `t` close → `t+1` open test | PASS |
| Engine/accounting/data tests | 32/32 PASS |
| Train/Validation candidate reconciliations | 18/18 PASS |
| Selected Development-Test reconciliation | PASS |
| Independent repeat manifest | Byte-identical PASS |

The run consumed 384,245 feature-panel rows, 555,949 full-history rows, 3,453 index rows, 88 corporate-action rows, and 69 removal-control rows. It generated 101,734 valid candidate rows over 3,327 dates after all gates. Thirty-nine mechanical actions and 49 reset actions were handled; 29,343 rows were blocked by corporate-action safety controls.

## Decision and interpretation

- **Accept as reference baseline:** yes. Later feature/ranking work now has a fixed, reproducible comparator.
- **Promote as trading candidate:** no. The D19 requirement failed in Validation and again in the one permitted Development-Test confirmation.
- **Open final OOS:** no. 2024–2025 remains sealed for Phase 8.
- **Start Phase 4 automatically:** no. This report stops at the Phase-3 approval gate.

The poor result is useful evidence: the transparent dual-momentum rule does not justify trading under these costs and turnover. It must remain in the registry rather than be rewritten after observing the outcome.

## Reproducibility identifiers

- Data hash: `b27027d8c4b4271ef9d80058890894791c339891a276d7c0bf747fead697da7f`
- Code hash: `0bdd6ac2fcb9d93de67eedab327c83ab2870709359c427a7fbb07dd1be2878dd`
- Config hash: `a3f77e02c103d4ebff357976a8d0f7b9f616d9a8b93066bc0b4bf8a1f8a337f9`
- Artifact-manifest hash: `dc24683a6981f57275cebde1245a9a438a5405edab6d50a137f967dd6d0fe64a`
