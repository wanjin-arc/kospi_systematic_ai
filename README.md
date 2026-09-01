# KOSPI 200 Fundamental+Technical Systematic Trading AI

현재 기본 연구선은 v2다. 기존 KOSPI 100 Technical Phase 0~5I는 재현 가능한 legacy 기록으로 보존하며, 새 KOSPI 200 모델의 독립 검증 근거로 재사용하지 않는다.

v2는 날짜별 실제 KOSPI 200 구성종목, KRX 일봉, 실제 DART 접수일 이후에만 사용 가능한 분기 재무제표, 분리된 Fundamental/Technical ranker와 사전등록 meta 결합을 목표로 한다. 현재 실제 수집·PIT 정규화·identity 동결·표준 XBRL taxonomy·일별 20개 Factor 패널 감사까지 완료했고 모델이나 백테스트는 실행하지 않았다.

- 설계: `docs/V2_FUNDAMENTAL_TECHNICAL_ARCHITECTURE_KO.md`
- 수집 안내: `docs/KOSPI200_V2_DATA_COLLECTION_KO.md`
- KRX 수집기: `tools/collect_krx_kospi200_v2.py`
- DART 수집기: `tools/collect_dart_kospi200_fundamentals_v2.py`
- PIT 정규화: `tools/normalize_dart_kospi200_fundamentals_v2.py`
- Factor 계약: `configs/fundamental_factor_contract_v1.json`
- Identity 계약: `configs/kospi200_identity_contract_v1.json`
- Account taxonomy: `configs/kospi200_fundamental_account_taxonomy_v1.json`

Current gate: **v2 C3 implemented real PyTorch LSTM volatility and CNN 2:1-event branches and improved model diagnostics, but D3's fixed 0.05/0.075 sizing policy overtraded and trailed the official KOSPI 200 by 54.91%p. No trading candidate is approved.**

Phase 1 v24 provides audited point-in-time daily data. Phase 2 adds a deterministic long-only daily execution/accounting engine. Phase 3 freezes and evaluates a transparent dual-momentum rule baseline. Phase 4 accepts `reversal_5` as the original Phase-5 input candidate. The original Phase 5 and the later Phase 5B both failed their cost-aware benchmark gates. Development Test remains unaccessed for these model experiments, and there is no approved timing model or brokerage integration.

## Implemented

- Point-in-time KOSPI 100 memberships, stock/index daily OHLCV, corporate-action controls, and intraday coverage audit.
- Ordinary development access refuses final-OOS dates.
- Frozen-order daily backtest engine with whole shares, cash limits, gaps, halts, partial fills, costs, stops/targets, and corporate actions.
- Cash, position, fill, equity, trade, audit, metric, and reconciliation outputs.
- Deterministic hashes and byte-identical artifact serialization.
- Phase-3 close/SMA200 plus 126-session excess-momentum rank, evaluated across only nine predeclared `H × N` combinations.
- Validation-only selection of `H=20, N=10`; reference accepted, trading candidate rejected.
- Phase-4 point-in-time features, executable 10-session open-to-open excess-return labels, univariate IC/HAC/coverage/stability/redundancy gates, and deterministic audit outputs.
- Phase-4 result: `reversal_5` accepted only as a Phase-5 input candidate; 20 other features held under the frozen gates.
- Original Phase-5 one-feature ranking selection: `tree_d3_l002` was diagnostic-best but failed the annual Validation excess-return gate.
- Phase-4B 2011–2018 internal audit of 21 stock features, five contemporaneous regime variables, and six fixed interactions.
- Phase-5B daily stock score and cross-sectional rank pipeline with seven preregistered candidates; all candidates rejected, diagnostic-best `elastic_a005_l02`.

Specifications and gate evidence:

- `docs/DATA_SPEC.md`
- `docs/BACKTEST_SPEC.md`
- `docs/PHASE2_VALIDATION_REPORT.md`
- `docs/BASELINE_SPEC.md`
- `docs/PHASE3_VALIDATION_REPORT.md`
- `docs/stages/phase_4_spec.md`
- `docs/stages/phase_4_report.md`
- `docs/stages/phase_4b_spec.md`
- `docs/stages/phase_4b_report.md`
- `docs/stages/phase_5_spec.md`
- `docs/stages/phase_5_report.md`
- `docs/stages/phase_5b_spec.md`
- `docs/stages/phase_5b_report.md`
- `data/quality/v24/phase1_v24_independent_audit.json`

## Verify

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kospi100_backtest.demo \
  --output artifacts/phase2/synthetic_reference
PYTHONPATH=src python -m kospi100_baseline.cli run \
  --config configs/phase3_baseline.json \
  --output artifacts/phase3
PYTHONPATH=src python -m kospi100_features.cli run \
  --config configs/phase4_features.json \
  --output artifacts/phase4
PYTHONPATH=src python -m kospi100_multifactor.cli analyze \
  --config configs/phase4b_multifactor.json \
  --output artifacts/phase4b_multifactor
PYTHONPATH=src python -m kospi100_multifactor.cli select \
  --config configs/phase5b_multifactor_ranking.json \
  --output artifacts/phase5b/selection
```

The test suite uses synthetic execution data. Synthetic performance is a calculation check, not a strategy result. The Phase-2 demo does not open the sealed final OOS.

## Key directories

- `src/kospi100_data/`: Phase-1 audit, partition, and guarded access.
- `src/kospi100_backtest/`: Phase-2 engine, costs, metrics, and deterministic writers.
- `src/kospi100_baseline/`: Phase-3 data guard, features, rule orders, selection, and reporting.
- `src/kospi100_features/`: Phase-4 feature, label, univariate evaluation, guarded runner, and CLI.
- `src/kospi100_ranking/`: original Phase-5 one-feature rank-model selection.
- `src/kospi100_multifactor/`: Phase-4B/5B feature audit, daily multifactor scores, ranking models, and guarded runners.
- `configs/`: frozen engine and KOSPI sell-cost schedules.
- `artifacts/phase2/synthetic_reference/`: reference ledgers and performance output.
- `artifacts/phase3/`: Phase-3 sensitivity, selected-period ledgers, metrics, and manifests.
- `artifacts/phase4/`: Phase-4 metrics, decisions, data audit, and deterministic manifest.
- `artifacts/phase4b_multifactor/`: Train-internal multifactor diagnostics and audit.
- `artifacts/phase5b/selection/`: rejected-candidate metrics, diagnostic model, score contract, and manifest.
- `data/processed/v24/development/`: development-only daily data through 2023.
- `data/sealed/final_oos_v24/`: Phase-8-only final OOS; do not use for development.
> 최신 v2 진단: Agent C4의 직접 초과수익 LSTM·CNN 모델과 Agent D4의 저회전 no-trade 포트폴리오는 구현·재현됐지만 공식 KOSPI200 대비 실패해 거래 후보가 아니다. 2019~2023은 소비된 개발기간이므로 추가 임계값 튜닝에 사용하지 않는다.
