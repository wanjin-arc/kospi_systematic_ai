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

## 원 실행 Codex Handoff — 당시 기록

- 다음 허용 단계: 사용자 승인 후 Phase 5 Ranking 모델 명세와 새 Experiment ID 사전 등록
- Phase 5 후보 입력: `reversal_5` 한 개
- 금지: 이번 Phase 4 결과를 근거로 기존 변수 공식·threshold·기간을 소급 변경하거나 Development Test/Final OOS를 조회하는 행위
- 재현 명령: `PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4`
- 회귀 명령: `PYTHONPATH=src python -m unittest discover -s tests -v`
- 완료 상태: Phase 4 단변량 화면 완료; 모델·포트폴리오·거래 후보 판정은 미수행

## Work Research Review

**검토일:** 2026-08-19
**검토 대상:** draft PR #1 `Complete Phase 4 feature research`, branch `phase-4`, head `197ad7f82377e730f4c1718972d03c13f0bdcc98`

이번 검토는 기존 산출물의 연구 정합성 감사다. Phase 4 결과를 다시 계산하거나 변수 결정·수치를 변경하지 않았다. Final OOS와 2022–2023 Development Test 행도 직접 열거나 평가하지 않았다.

### 확인된 사항

1. 21개 변수의 결정 분포와 `reversal_5` 단독 `채택_Phase5후보` 판정은 `feature_decisions.csv`, `feature_metrics.csv`, `annual_ic.csv` 및 사전 등록 gate와 일치한다.
2. `reversal_5`는 Train·Validation 방향이 모두 양수이고, Validation coverage 0.999365678569, 평균 IC 0.0243917510589, HAC t값 1.98746970018, 양(+) 연도 3/3으로 채택 기준을 통과한다.
3. 모든 변수의 Train·Validation coverage가 0.95 이상이므로 `폐기_결측과다`가 없는 결과는 타당하다.
4. `reversal_5`와 다른 변수의 Train 순위상관 절댓값 최대치는 0.90 미만이어서 중복 gate를 통과한다. 0.90 이상인 다른 변수 쌍은 선행 방향·안정성 gate에서 이미 보류됐으므로 채택 결과에 영향을 주지 않는다.
5. Feature는 동시점 membership·entry eligibility·tradable·rank eligibility와 CA blackout을 적용한다. Label은 `t` 종가 신호 뒤 `t+1` 시가 진입과 `t+11` 시가 종료를 사용하고 reset crossing을 제외한다. 계산·평가 입력 최대일은 2021-12-31, 최대 평가 신호일은 2021-12-02다.
6. Final OOS 경로 차단, manifest의 `final_oos_accessed=false`, 현재 작업공간의 봉인 경로 부재를 확인했다. Final OOS 접근 증거는 발견되지 않았다.
7. manifest가 기록한 7개 산출물 SHA-256, 설정 hash 및 source hash가 현재 branch 파일과 일치한다. 전체 회귀 테스트는 재검토 시점에도 43/43 통과했다.

### 완료 차단 문제

Phase 4 계산·평가와 변수 선택에 2022–2023 행이 사용되지 않은 것은 확인됐다. 그러나 `load_phase4_bundle()`은 최대일 2023-12-28인 개발 CSV 전체를 `pandas.read_csv()`로 읽은 뒤 `run_phase4()`에서 2021-12-31 이하로 자른다. 따라서 다음 두 진술은 구분해야 한다.

- `Development Test 계산·평가·선택 0행`: 확인됨
- `Development Test 미접근` 또는 registry의 `NOT_ACCESSED`: 실제 I/O 동작과 불일치

이 문제는 현재 보고된 IC·HAC·coverage 수치를 임의로 무효화하거나 다른 변수 결론으로 바꾸는 근거는 아니다. 다만 명세의 엄격한 Development Test 비접근 조건과 감사 기록의 의미가 일치하지 않으므로, Phase 4 완료 승인과 Phase 5 명세 작성은 보류한다.

또한 요청된 `docs/CURRENT_PROJECT_STATE.md`는 현재 branch에 존재하지 않는다. 기존 `docs/CURRENT_STATE_AND_CODEX_HANDOFF.md`가 유사 역할을 하지만 파일 계약이 다르므로 자동 대체하지 않는다.

### 재검증 필요 항목

1. 2021-12-31 이하로 물리 분리된 Train/Validation 전용 입력과 별도 manifest를 사용하거나, Development Test 행을 파싱·로드하지 않는 입력 경계를 구현한다.
2. `loaded`, `calculated`, `evaluated`, `selected`를 구분하는 감사 필드를 추가하고 registry의 `NOT_ACCESSED` 의미를 코드와 문서에서 동일하게 정의한다.
3. Development Test 행이 로드 단계에 도달하면 실패하는 테스트를 추가한다.
4. 결과를 이미 확인했으므로 기존 Experiment ID와 결과를 덮어쓰지 않는다. 동일 후보·기간·gate를 유지한 별도 재검증 Experiment ID로 경계 수정의 결과 동일성과 hash를 기록한다.
5. 재검증이 통과한 뒤에만 Phase 4 완료 상태, registry의 연구 검토 결정, `docs/CURRENT_PROJECT_STATE.md` 및 Phase 5 명세를 확정한다.

**Work 연구 검토 결론:** 기존 변수 수치와 `reversal_5` 후보 판정은 유지한다. Development Test 비접근 증거가 불충분하므로 Phase 4 완료 승인은 보류하며, Phase 5 spec은 작성하지 않는다.

## 입력 경계 교정 및 물리 재검증 완료

**작업 기간:** 2026-08-19~2026-08-22

**재검증 Experiment ID:** `P4-REVALIDATION-20260819-001`

**최종 상태:** `accept_boundary_revalidation_phase4_complete`

기존 구현의 통합 development 선로드 문제를 해소하기 위해 연구 로더를 `phase4_train_validation` 역할의 2021년 이하 전용 파티션만 허용하도록 교정했다. 로더는 데이터 파일 read 전에 partition 역할·최대일과 확장 manifest를 검증하고, 허용된 네 파일의 bytes·SHA-256·날짜 열·최소일·최대일·행 수를 대조한다. 로드 뒤 날짜 필터링은 하지 않는다.

### 물리 입력 생성

사용자 승인에 따라 `kospi100_data.phase4_partition` 상류 빌더를 추가했다. 빌더는 `data/processed/v24/development/`의 등록 source hash를 검증한 뒤 날짜 열 기준 스트리밍 cutoff로 다음 파일만 `data/processed/v24/phase4_train_validation_2021/`에 생성한다.

| 파일 | 행 수 | 최소일 | 최대일 |
|---|---:|---:|---:|
| `corporate_actions.csv.gz` | 78 | 2010-05-10 | 2021-12-30 |
| `feature_price_panel.csv.gz` | 333,301 | 2008-12-02 | 2021-12-30 |
| `full_history_ohlcv.csv.gz` | 478,301 | 2008-01-02 | 2021-12-30 |
| `index_ohlcv.csv.gz` | 2,962 | 2010-01-04 | 2021-12-30 |

이 상류 준비 단계는 2022~2023 행의 날짜를 경계 판정에만 사용하며 제외 행을 출력·보존·집계·연구 계산하지 않는다. Phase 4 연구 실행은 생성된 2021년 이하 네 파일만 읽는다. Final OOS는 생성·검증·실행 어느 단계에서도 접근하지 않았다. 물리 입력은 대용량 파생 데이터이므로 Git 추적 대상이 아니며 빌더·manifest 계약·hash로 재현한다.

### 실행 전 동결 hash

- 연구 설정: `2b65169985cf800c05863191e4f19bcb190865a92bd31b325f5be3f299cd7091`
- 재검증 설정: `71199d3c36e6d63775cfe5aaad4c8a59c3030f56f6a772130b3be12da0c75317`
- 재검증 source: `868457ef97de3c180bbd5d4edfd5ebe581569241fd4e16df21945577dc003844`
- 재검증 data: `69590204b3c35e686267dac81fe1347c0e3639005586da2d2db32e35c76b840f`
- Feature data contract: `4728adbdd7b48077a6e96714c920d541d19cae0e1f73aaaf9c98ebaee6c0aa2d`
- 재검증 artifact manifest: `77992184d3c413a3066be363e442ed1e6de4210ef72b1b1b2cccfbceb9fc2bb6`

data hash와 최종 source/config hash는 실제 완료 실행 전에 registry에 고정했다. 감사 최상위 `filter_applied_after_load` 필드 누락은 연구 결과를 확인하기 전에 교정하고 source hash를 다시 고정했다.

### 재검증 결과

접근 감사는 다음 불변조건을 만족했다.

```json
{
  "development_test_input_loaded": false,
  "development_test_rows_loaded": 0,
  "development_test_rows_calculated": 0,
  "development_test_rows_evaluated": 0,
  "development_test_rows_selected": 0,
  "filter_applied_after_load": false,
  "final_oos_accessed": false
}
```

최대 로드일과 최대 계산 입력일은 모두 2021-12-30이다. 기존 `artifacts/phase4/`의 `annual_ic.csv`, `feature_decisions.csv`, `feature_metrics.csv`, `redundancy_matrix.csv`, `regime_feature_audit.csv`와 재검증 결과가 각각 byte-identical이었다. 따라서 21개 변수의 수치·결정 분포와 `reversal_5` 단독 `채택_Phase5후보` 판정은 변경되지 않았다.

물리 파티션 6개 구성 파일은 독립 재생성본과 모두 byte-identical이었고, 재검증 산출물 8개도 독립 재실행본과 모두 byte-identical이었다. Phase 4 전용 테스트 18/18과 전체 회귀 테스트 50/50이 통과했다.

**Work 연구 검토 최종 결론:** 2026-08-19에 지적된 Development Test 입력 경계 문제와 증거 누락은 해소됐다. 기존 연구 결론을 변경하지 않은 채 완료 조건을 모두 충족했으므로 Phase 4 완료를 승인한다. Phase 5는 아직 시작하지 않는다.

## Codex Handoff

- 완료 상태: Phase 4 validated, `P4-REVALIDATION-20260819-001` completed
- Phase 5 허용 후보 입력: `reversal_5` 한 개
- 물리 파티션 생성 명령: `PYTHONPATH=src python -m kospi100_data.phase4_partition --source-root data/processed/v24/development --output-root data/processed/v24/phase4_train_validation_2021`
- 재검증 명령: `PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_revalidation_20260819.json --output artifacts/phase4_revalidation_20260819`
- 회귀 명령: `PYTHONPATH=src python -m unittest discover -s tests -v`
- 다음 허용 작업: 사용자 승인 후 Phase 5 명세와 새 Experiment ID를 결과 확인 전에 등록
- 금지: Phase 4 결과·기간·gate 소급 변경, 승인 전 Phase 5 실행, Development Test 연구 사용, Final OOS 접근
