# Phase 4 단계 명세 — 기술적 변수 단변량 연구

## 1. 단계 정보

- 단계/이름: Phase 4 / Technical Feature Research
- Experiment ID: `P4-FEATURES-20260818-001`
- 상태: preregistered / 부분 구현 / 미실행
- 작성일: 2026-08-19
- 이전 단계 기준 버전: Phase 1 v24 데이터 감사 PASS, Phase 2 엔진 완료, Phase 3 기준선 완료·거래 후보 탈락
- 동결 설정: `configs/phase4_features.json` (`phase4-features-v1`)

## 2. 이번 단계 결론

Phase 4는 사전 등록된 21개 횡단면 기술 변수와 5개 시장상태 변수를 계산하고, **Train/Validation 단변량 검증만** 수행한다. 이 단계는 Ranking 모델 학습, 포트폴리오 구성, 백테스트 또는 거래 규칙 선택을 수행하지 않는다.

현재는 설정과 일부 계산 모듈만 존재한다. `runner.py`, `cli.py`, Phase 4 테스트, 실행 산출물 및 결과 보고서가 없으므로, Phase 4는 완료 또는 검증 상태가 아니다.

## 3. 목적과 비목표

### 목적

- 동시점 KOSPI 100 Universe에서 계산 가능한 가격·거래량·거래대금 기반 후보 변수의 단변량 횡단면 관계를 확인한다.
- 각 변수의 결측 coverage, 일별 Spearman IC, HAC t값, 연도별 안정성 및 변수 간 중복을 사전 등록 기준으로 평가한다.
- 모든 기준을 통과한 변수만 Phase 5 Ranking 모델의 **후보**로 기록한다. 이는 모델 채택이나 거래 채택이 아니다.
- 시장상태 변수 5개는 계산·coverage 감사만 하고, Phase 7 전까지 보류한다.

### 이번 단계에서 하지 않을 일

- 모델 학습, 하이퍼파라미터 탐색, scaler·winsorization·imputer·feature selection의 적합
- 포트폴리오 백테스트, 비용·slippage 성과 비교, 거래 후보 선정
- Development Test(2022–2023) 또는 Final OOS(2024–2025) 접근·평가·집계
- 데이터 재수집·재처리, Raw OHLCV 수정, Corporate Action 규칙 변경
- 사전 등록된 후보군, 기간, label, 임계값의 결과 기반 변경
- Phase 5 이후 구현

## 4. 변경 전 가설

- 가설: 가격·거래량·거래대금만으로 계산되는 일부 기술 변수는 실행 가능한 10거래일 선행 KOSPI 100 초과수익과 시간적으로 안정적인 양(+)의 단변량 횡단면 관계를 보일 수 있다.
- 기대 방향: 설정의 모든 횡단면 변수는 부호 변환을 포함해 양(+)의 일별 Spearman IC를 기대한다.
- 실패 가능 시장 상태: 횡단면 모멘텀이 붕괴하는 급격한 반전장, 유동성·거래량이 비정상적인 장, 변동성 급등장, Corporate Action reset 또는 결측으로 유효 lookback이 부족한 구간.
- 채택/폐기 기준: 제6절과 제8절의 사전 등록 gate를 사용한다. 결과 확인 뒤 기준을 바꾸지 않는다.

## 5. 입력 계약

| 입력 | 경로/버전 | 키·필수 컬럼 | 허용 기간 | 계산 가능 시점 |
|---|---|---|---|---|
| Feature price panel | `data/processed/v24/development/feature_price_panel.csv.gz` | `date, security_id, open, high, low, close, feature_volume, feature_trading_value, is_member, eligible_new_entry, tradable, rank_eligible` | 개발 파티션만; 평가 행은 2021-12-31 이하 | `t` 장 종료 뒤 |
| Full history OHLCV | `data/processed/v24/development/full_history_ohlcv.csv.gz` | `date, security_id, open, tradable` 및 식별·상태 컬럼 | 개발 파티션만; label은 2021년 평가 경계 안에서 완결 | `t+1`, `t+11` 시가 label에만 사용 |
| KOSPI 100 index | `data/processed/v24/development/index_ohlcv.csv.gz` | `date, open, close` | 개발 파티션만 | index 기술 변수는 `t` 종가, label은 미래 시가 |
| Corporate actions | `data/processed/v24/development/corporate_actions.csv.gz` | `security_id, canonical_event_id, feature_handling, feature_boundary_date, price_multiplier, share_multiplier, first_filing_date, portfolio_terms_status` | 개발 파티션만 | 해당 시점에 알려진 처리 규칙만 |
| 개발 manifest·partition | `data/processed/v24/development/manifest.csv`, `partition.json` | 파일 hash, role, max date | role=`development`, max date=`2023-12-31` | 로드 전 검증 |
| Feature data contract | `data/contracts/feature_data_contract_v24.json` | v24 schema·데이터 계약 | 계약 파일 자체만 | 로드 전 검증 |
| 동결 설정 | `configs/phase4_features.json` | Experiment ID, 기간, label, 변수, gate | 전체 | 실행 전 hash 기록 |

입력 root가 `sealed` 또는 `final_oos_v24`를 포함하면 즉시 실패한다. 데이터 root, partition role, manifest hash, 실제 최대 날짜를 모두 검증한다. Feature 계산은 `t` 종료 시점까지 확정된 데이터만 사용한다.

## 6. 계산/평가 명세

### 6.1 공통 계산 규칙

- Universe: 신호일 `t`에 `is_member`, `eligible_new_entry`, `tradable`, `rank_eligible`가 모두 참인 행만 횡단면 평가 대상으로 한다.
- 가격: Raw OHLCV는 수정하지 않는다. 기계적 Corporate Action은 Point-in-Time 연속 Feature 계산에만 적용한다.
- Reset: `RESET_` Corporate Action 경계를 넘는 rolling window와 forward label은 제외한다. 미결 portfolio terms 또는 blackout 행은 평가 대상에서 제외한다.
- 세션 연속성: lookback은 달력일이 아니라 index 거래 세션 수로 계산한다. 중간 세션 누락 또는 segment 변경이 있으면 해당 lookback 결과는 결측이다.
- Breadth: 신호일의 `is_member` 및 `eligible_new_entry` Universe를 분모로 하고, 결측 Feature는 `False`로 계산하되 coverage를 함께 기록한다.
- 횡단면 통계: 날짜별 유효 종목 수가 30개 이상일 때만 Spearman IC와 상·하위 quintile label spread를 계산한다.

### 6.2 횡단면 변수 21개

| ID | 계열 | 공식 | 입력·lookback | 기대 방향 |
|---|---|---|---|---|
| `reversal_5` | reversal | `-(close / close_lag5 - 1)` | 연속 가격, 5세션 | 양(+) |
| `momentum_20` | momentum | `close / close_lag20 - 1` | 연속 가격, 20세션 | 양(+) |
| `momentum_63` | momentum | `close / close_lag63 - 1` | 연속 가격, 63세션 | 양(+) |
| `momentum_126` | momentum | `close / close_lag126 - 1` | 연속 가격, 126세션 | 양(+) |
| `momentum_252` | momentum | `close / close_lag252 - 1` | 연속 가격, 252세션 | 양(+) |
| `excess_momentum_20` | relative momentum | `stock_return20 - index_return20` | 종목·지수 종가, 20세션 | 양(+) |
| `excess_momentum_63` | relative momentum | `stock_return63 - index_return63` | 종목·지수 종가, 63세션 | 양(+) |
| `excess_momentum_126` | relative momentum | `stock_return126 - index_return126` | 종목·지수 종가, 126세션 | 양(+) |
| `trend_close_sma20` | trend | `close / sma20 - 1` | 연속 가격, 20세션 | 양(+) |
| `trend_close_sma60` | trend | `close / sma60 - 1` | 연속 가격, 60세션 | 양(+) |
| `trend_close_sma200` | trend | `close / sma200 - 1` | 연속 가격, 200세션 | 양(+) |
| `trend_sma20_sma60` | trend | `sma20 / sma60 - 1` | 연속 가격, 60세션 | 양(+) |
| `high_proximity_252` | breakout | `close / rolling_max_close252 - 1` | 연속 가격, 252세션 | 양(+) |
| `low_volatility_20` | risk | `-std(log_return1, 20) * sqrt(252)` | 로그수익률, 20세션 | 양(+) |
| `low_downside_volatility_20` | risk | `-sqrt(mean(min(log_return1, 0)^2, 20)) * sqrt(252)` | 로그수익률, 20세션 | 양(+) |
| `low_atr_20` | risk | `-mean(true_range, 20) / close` | 고·저·종가, 20세션 | 양(+) |
| `risk_adjusted_momentum_63` | risk-adjusted momentum | `momentum63 / annualized_volatility20` | 수익률·변동성, 63세션 | 양(+) |
| `volume_confirmation_5_20` | activity | `mean(feature_volume, 5) / mean(feature_volume, 20) - 1` | 조정 거래량, 20세션 | 양(+) |
| `trading_value_confirmation_5_20` | activity | `mean(feature_trading_value, 5) / mean(feature_trading_value, 20) - 1` | 거래대금, 20세션 | 양(+) |
| `liquidity_20` | liquidity | `log1p(mean(feature_trading_value, 20))` | 거래대금, 20세션 | 양(+) |
| `low_illiquidity_20` | liquidity | `-mean(abs(log_return1) / (feature_trading_value / 1e9), 20)` | 로그수익률·거래대금, 20세션 | 양(+) |

각 변수는 `t` 종가까지의 완성 일봉만으로 계산한다. 미래 bar, 미래 membership, 미래 Corporate Action 정보 또는 `t+1` 가격을 Feature에 사용해서는 안 된다.

### 6.3 시장상태 변수 5개

| ID | 공식 | 가용 시점 | 결정 |
|---|---|---|---|
| `index_trend_200` | `index_close / index_sma200 - 1` | `t` 종가 | 계산·감사 후 보류 |
| `index_momentum_63` | `index_close / index_close_lag63 - 1` | `t` 종가 | 계산·감사 후 보류 |
| `index_low_volatility_20` | `-std(index_log_return1, 20) * sqrt(252)` | `t` 종가 | 계산·감사 후 보류 |
| `breadth_above_sma200` | `mean(member_close > member_sma200)` | `t` 종가 | 계산·감사 후 보류 |
| `breadth_positive_momentum20` | `mean(member_return20 > 0)` | `t` 종가 | 계산·감사 후 보류 |

### 6.4 Label

Label 이름은 `forward_10_session_excess_open_to_open_log_return`이다.

```text
log(stock_open[t+11] / stock_open[t+1])
- log(index_open[t+11] / index_open[t+1])
```

- 신호 시점: `t` 거래일의 공식 장 종료 뒤
- 진입 시점: 다음 거래 세션 `t+1` 시가
- 종료 시점: 10개의 완전한 거래 세션 간격 뒤인 `t+11` 시가
- 종목·지수 진입 및 종료 시가가 유한하고 양수이며, 종목 진입·종료가 모두 tradable일 때만 유효하다.
- `t < t+1 < t+11` 시간 순서를 assertion으로 검증한다.
- reset segment를 교차하거나 forward horizon이 완결되지 않은 행은 결측 처리하고 fitting·평가에서 제외한다.

### 6.5 평가와 결정 규칙

평가 구간은 Train(2011–2018)과 Validation(2019–2021)만이다. 각 변수는 일별 Spearman IC, 상·하위 quintile label spread, coverage, 연도별 평균 IC를 계산한다. HAC t값은 일별 IC에 Newey-West형 Bartlett 가중을 적용하고 lag는 10세션이다.

| 결정 | 사전 등록 기준 |
|---|---|
| `채택_Phase5후보` | Train·Validation coverage 각각 0.95 이상, Train 평균 IC > 0, Validation 평균 IC > 0, Validation HAC t값 1.0 이상, Validation 양(+) IC 연도 2개 이상, 더 강한 채택 변수와 Train 순위상관 절댓값 0.90 미만 |
| `폐기_결측과다` | Train 또는 Validation coverage가 0.95 미만 |
| `보류_학습방향불일치` | Train 평균 IC가 양(+)이 아님 |
| `보류_검증방향불일치` | Validation 평균 IC가 양(+)이 아님 |
| `보류_검증불안정` | Validation HAC t값이 1.0 미만 또는 계산 불가 |
| `보류_연도불안정` | Validation 양(+) IC 연도가 2개 미만 |
| `보류_중복` | 더 강한 채택 변수와 Train 횡단면 순위상관 절댓값이 0.90 이상 |
| regime 변수 | 계산·감사 후 `보류_Phase7` |

중복 비교의 우선순위는 Validation 평균 IC 내림차순, 동률이면 변수 ID 오름차순이다. 채택 변수는 Phase 5의 입력 후보일 뿐 모델 또는 거래 규칙의 채택 근거가 아니다.

## 7. 출력 계약

실행이 구현된 뒤에만 아래 산출물을 생성한다. 대용량 Feature panel 또는 Raw 데이터는 산출물로 Git 추적하지 않는다.

| 산출물 | 경로 | 스키마/형식 | 생성 조건 |
|---|---|---|---|
| 변수 지표 | `artifacts/phase4/feature_metrics.csv` | 변수·구간별 coverage, IC, HAC, spread, 연도 요약 | 정상 실행 |
| 연도별 IC | `artifacts/phase4/annual_ic.csv` | 변수·연도별 평균 IC | 정상 실행 |
| 중복 행렬 | `artifacts/phase4/redundancy_matrix.csv` | 변수×변수 Train 순위상관 | 정상 실행 |
| 변수 결정 | `artifacts/phase4/feature_decisions.csv` | 변수, 계열, 결정, 근거, 중복 상대 | 정상 실행 |
| regime 감사 | `artifacts/phase4/regime_feature_audit.csv` | 날짜, 5개 regime 값, coverage | 정상 실행 |
| 데이터 감사 | `artifacts/phase4/data_audit.json` | partition, manifest, 최대 로드 날짜, OOS 접근 여부, row counts | 정상 실행 |
| 실행 정보 | `artifacts/phase4/run.json` | Experiment ID, source/config/data hash, 명령, seed, 금지 작업 상태 | 정상 실행 |
| manifest | `artifacts/phase4/manifest.json` | 각 산출물 SHA-256 및 결정성 정보 | 정상 실행 |
| 단계 보고서 | `docs/stages/phase_4_report.md` | 실제 결과·문제·미결정 사항·Codex Handoff | 실행과 검증 완료 뒤 |
| 실험 등록 | `experiments/registry.csv` | 결과·해시·결정 필드 갱신 | 실행과 검증 완료 뒤 |

## 8. 연구 제약

- 허용 선택 구간: Train 2011–2018, Validation 2019–2021만.
- Development Test: 2022–2023은 Phase 4에서 로드 후 평가·선택·집계해서는 안 된다. 입력 bundle의 물리적 최대 날짜가 2023이어도 2022년 이후 평가 행은 fail-closed로 거부한다.
- Purge: 최대 선언 horizon 20세션을 사용한다. Train 끝의 마지막 20개 label 세션을 Validation 경계 전에 제거한다. Validation 끝의 마지막 20개 label 세션도 제거하여 Development Test 가격이 label에 들어오지 않게 한다.
- Embargo: 평가 블록 뒤 첫 20세션은 이후 학습에 재진입할 수 없다. 이 단일 순방향 Phase 4 화면에는 이후 학습 블록이 없으므로 실질적 적용 집합은 공집합일 수 있으나, 설정·감사·단위 테스트에는 반드시 표현한다.
- 금지 데이터: 재무제표, DART, 뉴스, 밸류에이션, 업종·기업 텍스트, 미래 OHLCV, 미래 Universe, 미래 Corporate Action 지식.
- 비용·slippage: 모델·포트폴리오·체결을 평가하지 않으므로 적용하지 않는다.
- protected OOS: `data/sealed/final_oos_v24/`는 Phase 8 전 열기·스캔·glob·요약·집계·테스트 입력에 사용하지 않는다. 해당 경로를 입력 또는 출력으로 지정하면 즉시 실패한다.
- Random split은 금지한다.

## 9. 테스트

### 단위 테스트

- 설정 버전, Experiment ID, 고정 Train/Validation 기간, 정확히 21개 횡단면 변수와 5개 regime 변수 검증
- `sealed`·`final_oos_v24` 경로, 잘못된 partition role, 잘못된 max date, Development Test 평가 요청 거부
- 각 변수의 첫 유효 lookback, 세션 연속성, 중간 결측, rank eligibility 및 minimum cross-section 경계
- Point-in-Time 기계적 Corporate Action 조정, reset segment 분리, late-notice blackout
- `t → t+1 → t+11` label 시점, 10세션 horizon, tradable 조건, reset crossing 제외
- purge 20세션과 embargo 20세션의 경계 불변조건
- 일별 Spearman IC, HAC lag 10, 연도별 IC, coverage, quintile spread
- 중복 임계값 0.90, 우선순위 및 결정값

### 통합·회귀 테스트

- development manifest와 hash를 검증한 합성 입력에서 `run_phase4`가 모든 구조화 산출물을 작성한다.
- 동일 입력·설정·seed의 독립 재실행에서 manifest와 결정 파일이 byte-identical이다.
- `import kospi100_features`와 registry의 `python -m kospi100_features.cli run --config ... --output ...` 명령이 성공한다.
- `PYTHONPATH=src python -m unittest discover -s tests -v` 전체 회귀 테스트가 통과한다.

## 10. 완료 조건

- [ ] `runner.py`와 `cli.py`가 존재하고 package import가 성공한다.
- [ ] development manifest, partition role, 최대 날짜 및 파일 hash를 검증한다.
- [ ] Train/Validation만 사용했고 Development Test·Final OOS가 미사용임을 감사 산출물로 증명한다.
- [ ] 21개 횡단면 변수와 5개 regime 변수의 공식·입력·lookback·시점·결정이 기록된다.
- [ ] 필수 구조화 산출물과 SHA-256 manifest가 생성된다.
- [ ] 단위·통합·전체 회귀 테스트가 통과한다.
- [ ] 동일 설정의 독립 재실행이 결정적이다.
- [ ] registry가 실행 전 코드·설정·데이터 hash와 실행 후 결과·결정으로 갱신된다.
- [ ] `docs/stages/phase_4_report.md`가 한글로 작성되고 마지막에 Codex Handoff를 포함한다.
- [ ] 모델 학습·포트폴리오 백테스트·Development Test·Final OOS 접근을 하지 않았다.

## 11. 발견된 문제와 미결정 사항

1. `src/kospi100_features/runner.py`와 `cli.py`가 없어 package import 및 registry 재현 명령이 실패한다.
2. Phase 4 전용 테스트, `artifacts/phase4/`, 변수 결정 결과 및 Phase 4 보고서가 없다.
3. 기존 평가 초안은 purge 값을 사용하지만 embargo의 실제 적용을 보장하는 runner·테스트가 없다. 단일 순방향 화면에서 embargo가 공집합임을 명시적으로 검증해야 한다.
4. 인계 문서의 Feature data contract 경로는 현재 `data/contracts/feature_data_contract_v24.json`이다. 구현은 이 canonical 경로를 사용하고, 문서가 다른 경로를 참조하면 정합화가 필요하다.
5. 현재 작업공간에는 `data/sealed/final_oos_v24/`와 봉인 manifest가 없다. Phase 4는 이를 복구하거나 읽지 않으며, Phase 8 이전에는 OOS 해시 manifest·스키마 계약의 별도 관리 방식만 결정할 수 있다.
6. P4 registry 행의 코드·설정 hash가 비어 있다. 결과를 보기 전에 현재 설정 hash와 구현 코드 hash를 기록해야 한다. 설정 내용을 변경해야 한다면 새 Experiment ID가 필요하다.

## 12. Codex Handoff

- 구현 대상 파일:
  - `src/kospi100_features/runner.py`
  - `src/kospi100_features/cli.py`
  - `tests/test_phase4_config.py`
  - `tests/test_phase4_features.py`
  - `tests/test_phase4_labels.py`
  - `tests/test_phase4_evaluate.py`
  - `tests/test_phase4_runner.py`
  - 실행 후 `docs/stages/phase_4_report.md`
- 기존 API:
  - `load_config(path) -> FeatureResearchConfig`
  - `build_feature_matrix(panel, index, actions) -> FeatureMatrixResult`
  - `attach_forward_label(feature_frame, full_history, index, actions) -> (DataFrame, audit)`
  - `evaluate_features(labeled, index, config) -> EvaluationResult`
- 새 공개 API:
  - `run_phase4(config_path: Path, output_dir: Path) -> dict[str, object]`
  - CLI: `python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4`
- 오류 처리:
  - sealed/OOS 경로, 비-development partition, manifest hash 불일치, 2022년 이후 평가행, 불완전한 필수 입력, 미래 시점 불변조건 위반은 fail-closed 예외로 종료한다.
  - 산출물은 임시 위치에서 완성·hash 검증 후 결정적으로 publish한다.
- 재현 명령:

```text
PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4
PYTHONPATH=src python -m unittest discover -s tests -v
```

- 완료 판정: 제10절의 모든 항목을 만족하고, 결과 보고서가 실제 실행 증거와 남은 위험을 기록할 때만 Phase 4를 validated 또는 rejected로 갱신한다. 결과가 없으면 상태는 preregistered / 부분 구현 / 미실행으로 유지한다.
