# Phase 4 실행 보고서 — 기술적 변수 단변량 연구

## 1. 실행 결론

Phase 4를 동결 설정 `phase4-features-v1`과 Experiment ID `P4-FEATURES-20260818-001`로 실행했다. 사전 등록한 21개 횡단면 변수 중 `reversal_5` 한 개가 Train·Validation coverage, IC 방향, Validation HAC t값, 연도 안정성 및 중복 기준을 모두 통과해 `채택_Phase5후보`로 기록됐다. 이는 Phase 5 입력 후보 판정일 뿐 모델 또는 거래 전략 채택이 아니다.

시장상태 변수 5개는 계산·coverage 감사만 수행했으며 모두 `보류_Phase7`로 유지했다. 모델 학습, 포트폴리오 구성, 백테스트, 비용·slippage 성과 평가는 수행하지 않았다.

## 2. 실행 경계와 재현 정보

- 실행일: 2026-08-19
- 명령: `PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4`
- 코드 hash: `f199ed4de175c1643877ed064670c15b6618e0010542230f3b60bff265997deb`
- 설정 hash: `2b65169985cf800c05863191e4f19bcb190865a92bd31b325f5be3f299cd7091`
- 데이터 hash: `b27027d8c4b4271ef9d80058890894791c339891a276d7c0bf747fead697da7f`
- 데이터 계약 hash: `4728adbdd7b48077a6e96714c920d541d19cae0e1f73aaaf9c98ebaee6c0aa2d`
- 계산 입력 최대일: 2021-12-31 이하, 실제 feature 최대 거래일 2021-12-30
- 평가 신호일: 2011-01-03~2021-12-02
- Development Test 계산·평가 행: 0
- Final OOS 접근: false

development 파티션의 물리적 최대 거래일은 2023-12-28이지만, 2022~2023 행은 manifest·파티션 경계와 파일 hash 검증에만 사용했다. Feature, label, regime 및 단변량 통계 입력은 2021-12-31 이하로 잘라 Development Test를 계산·집계하지 않았다. Validation 끝 20세션 purge로 2022년 가격 없이 label horizon을 완결했다.

Embargo는 동결값 20세션을 유지했다. Phase 4는 Validation 이후 재학습 블록이 없는 단일 순방향 화면이므로 실제 재진입 금지 날짜 집합은 공집합이며, 이 상태를 감사 결과와 테스트에 명시했다.

## 3. 데이터·시점 감사

- development manifest 파일 6개의 크기와 SHA-256을 검증했다.
- canonical 계약은 `data/contracts/feature_data_contract_v24.json` v24를 사용했다.
- Feature 행 333,301개 중 동시점 membership·eligible_new_entry·tradable·rank_eligible·CA blackout을 통과한 행은 270,559개였다.
- 완결된 10세션 선행 초과 log return label은 269,213개였다.
- reset 경계 교차로 제외한 label은 994개였다.
- Corporate Action 입력은 계산 종료일 이하의 기계적 조정 34건과 reset 44건만 사용했다.
- 평가 대상은 241,582행이었다.
- `t` 종가 이후 `t+1` 시가 진입, `t+11` 시가 종료 순서를 검증했다.
- Raw OHLCV 덮어쓰기, 미래 bar 사용, Development Test 선택, Final OOS 접근은 없었다.

## 4. 변수별 결과

| 변수 | Train 평균 IC | Validation 평균 IC | Validation HAC t | Validation 양(+) 연도 | 결정 |
|---|---:|---:|---:|---:|---|
| `excess_momentum_126` | -0.0085 | -0.0265 | -1.35 | 1/3 | 보류_학습방향불일치 |
| `excess_momentum_20` | -0.0059 | -0.0272 | -1.57 | 1/3 | 보류_학습방향불일치 |
| `excess_momentum_63` | -0.0044 | -0.0392 | -2.01 | 0/3 | 보류_학습방향불일치 |
| `high_proximity_252` | -0.0003 | -0.0164 | -0.75 | 0/3 | 보류_학습방향불일치 |
| `liquidity_20` | -0.0185 | 0.0207 | 1.31 | 2/3 | 보류_학습방향불일치 |
| `low_atr_20` | 0.0006 | 0.0198 | 1.24 | 1/3 | 보류_연도불안정 |
| `low_downside_volatility_20` | -0.0024 | 0.0060 | 0.37 | 2/3 | 보류_학습방향불일치 |
| `low_illiquidity_20` | -0.0174 | 0.0309 | 2.09 | 2/3 | 보류_학습방향불일치 |
| `low_volatility_20` | 0.0010 | 0.0109 | 0.75 | 2/3 | 보류_검증불안정 |
| `momentum_126` | -0.0085 | -0.0265 | -1.35 | 1/3 | 보류_학습방향불일치 |
| `momentum_20` | -0.0059 | -0.0272 | -1.57 | 1/3 | 보류_학습방향불일치 |
| `momentum_252` | 0.0050 | -0.0336 | -1.45 | 0/3 | 보류_검증방향불일치 |
| `momentum_63` | -0.0044 | -0.0392 | -2.01 | 0/3 | 보류_학습방향불일치 |
| `reversal_5` | 0.0175 | 0.0244 | 1.99 | 3/3 | 채택_Phase5후보 |
| `risk_adjusted_momentum_63` | -0.0024 | -0.0382 | -2.04 | 0/3 | 보류_학습방향불일치 |
| `trading_value_confirmation_5_20` | 0.0000 | -0.0130 | -1.33 | 1/3 | 보류_학습방향불일치 |
| `trend_close_sma20` | -0.0098 | -0.0184 | -1.18 | 0/3 | 보류_학습방향불일치 |
| `trend_close_sma200` | -0.0081 | -0.0418 | -1.89 | 0/3 | 보류_학습방향불일치 |
| `trend_close_sma60` | -0.0068 | -0.0373 | -1.98 | 0/3 | 보류_학습방향불일치 |
| `trend_sma20_sma60` | -0.0083 | -0.0419 | -2.16 | 1/3 | 보류_학습방향불일치 |
| `volume_confirmation_5_20` | 0.0015 | -0.0109 | -1.10 | 1/3 | 보류_검증방향불일치 |

결정 분포는 `채택_Phase5후보` 1개, `보류_학습방향불일치` 16개, `보류_검증방향불일치` 2개, `보류_검증불안정` 1개, `보류_연도불안정` 1개다. coverage 부족 폐기와 중복 보류는 없었다.

`reversal_5`의 Train coverage는 0.9998, 평균 IC는 0.01754, HAC t값은 2.31이었다. Validation coverage는 0.9994, 평균 IC는 0.02439, HAC t값은 1.99였고 2019~2021 세 연도의 평균 IC가 모두 양수였다.

변수 공식·입력·lookback·가용 시점·기대 방향·공통 실패 조건·누수 통제는 `docs/stages/phase_4_spec.md` 제4~6절을 따른다. 구조화된 기간별 지표, 연도별 IC, 중복 행렬 및 결정 근거는 `artifacts/phase4/`에 기록했다.

## 5. 테스트와 결정성

- Phase 4 전용 테스트: 11/11 PASS
- 전체 회귀 테스트: 기존 32개 포함 43/43 PASS
- package import와 registry CLI 형식: PASS
- 합성 runner manifest/file hash 검증: PASS
- 실제 development 데이터 독립 재실행: 8개 산출물 모두 byte-identical
- manifest 내부 파일 SHA-256 재검증: PASS

## 6. 산출물

- `artifacts/phase4/feature_metrics.csv`
- `artifacts/phase4/annual_ic.csv`
- `artifacts/phase4/redundancy_matrix.csv`
- `artifacts/phase4/feature_decisions.csv`
- `artifacts/phase4/regime_feature_audit.csv`
- `artifacts/phase4/data_audit.json`
- `artifacts/phase4/run.json`
- `artifacts/phase4/manifest.json`

## 7. 남은 문제와 미결정 사항

1. `reversal_5`는 단변량 후보일 뿐이며 Phase 5 모델 입력 채택 여부는 별도 사전 등록·시간순서 검증이 필요하다.
2. Phase 4에서는 Development Test를 사용하지 않았으므로 2022~2023 안정성에 대한 결론을 내릴 수 없다.
3. 시장상태 변수는 Phase 7 전까지 보류하며, 이번 결과로 regime 임계값을 정하지 않는다.
4. Final OOS는 Phase 8 단일 릴리스 전까지 계속 봉인한다.

## Codex Handoff

- 다음 허용 단계: 사용자 승인 후 Phase 5 Ranking 모델 명세와 새 Experiment ID 사전 등록
- Phase 5 후보 입력: `reversal_5` 한 개
- 금지: 이번 Phase 4 결과를 근거로 기존 변수 공식·threshold·기간을 소급 변경하거나 Development Test/Final OOS를 조회하는 행위
- 재현 명령: `PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4`
- 회귀 명령: `PYTHONPATH=src python -m unittest discover -s tests -v`
- 완료 상태: Phase 4 단변량 화면 완료; 모델·포트폴리오·거래 후보 판정은 미수행
