# Phase 4B 다변수 기술 신호 명세

## 1. 목적과 승인 근거

기존 Phase 5는 `reversal_5` 하나를 서로 다른 함수로 변환했으며, 선택 모델의 2019~2021 연결 Validation 순초과수익률은 -42.4565%p였다. 전략 수익률은 +7.9429%였지만 KOSPI 100 가격지수 +50.3994%를 따라가지 못했고 연도별 순초과수익률 gate는 0/3이었다.

사용자는 2026-08-23에 기존 결과를 덮어쓰지 않는 새 Phase 4B와 새 모델 연구를 승인했다. 이번 단계의 가설은 단일 단기 반전 변수의 정보 부족을 보완하기 위해 가격 추세, 상대 모멘텀, 변동성, 거래활동, 유동성 및 동시점 시장상태를 함께 사용하면 매일의 종목별 상대 점수에 더 안정적인 정보가 생길 수 있다는 것이다.

## 2. 데이터 경계

- 연구 계산 입력은 `data/processed/v24/phase4b_train_internal_2018/` 하나다.
- 파티션 역할은 `phase4b_train_internal`, 최대 날짜는 2018-12-31이다.
- 2019~2021은 기존 실험에서 이미 소비된 Validation이므로 새 Feature·모델 선택 계산에 사용하지 않는다.
- Development Test는 로드·계산·평가·선택하지 않는다.
- 봉인된 Final OOS는 접근하지 않는다.
- 파티션은 검증된 2021년 이하 Selection 파티션에서 파생하되 연구 runner는 2018년 이하 물리 파티션만 읽는다.
- Raw 데이터는 수정하지 않는다.

## 3. Feature와 점수 계약

- Phase 4의 21개 종목 기술변수를 모두 재계산한다.
- 종목 변수는 날짜별 KOSPI 100 적격 횡단면에서 average percentile rank로 변환한다.
- 시장상태 5개는 각 fold의 Train 날짜만으로 중앙값 대체와 표준화를 적합한다.
- 6개 상호작용은 설정 파일에 고정하며 결과 확인 후 추가·삭제하지 않는다.
- `t`일 종가까지의 정보로 점수를 만들고 `t+1` 이후에만 주문할 수 있다.
- target은 `t+1` 시가 진입, `t+11` 시가 청산의 10세션 KOSPI 100 초과수익률 횡단면 순위다.

## 4. 내부 검증

공식 2019~2021 Validation을 다시 최적화하지 않기 위해 2011~2018 Train 안에 다음 anchored fold를 둔다.

| fold | Train | 내부 Validation |
|---|---|---|
| I2015 | 2011~2014 | 2015 |
| I2016 | 2011~2015 | 2016 |
| I2017 | 2011~2016 | 2017 |
| I2018 | 2011~2017 | 2018 |

각 fold는 거래소 세션 기준 purge 20과 embargo 20을 적용한다. Feature coverage, 일별 Spearman IC, HAC lag 10, 연도별 방향, 중복 및 데이터 경계를 감사한다. Phase 4B는 모델이나 포트폴리오를 선택하지 않는다.

## 5. 산출물

- `artifacts/phase4b_multifactor/feature_diagnostics.csv`
- `artifacts/phase4b_multifactor/fold_feature_metrics.csv`
- `artifacts/phase4b_multifactor/failure_analysis.json`
- `artifacts/phase4b_multifactor/data_audit.json`
- `artifacts/phase4b_multifactor/run.json`
- `artifacts/phase4b_multifactor/manifest.json`

## 6. 테스트와 완료 조건

- 설정 버전·변수 개수·상호작용·기간 guard
- 2018년 이후 manifest를 data reader 호출 전에 거부
- Development Test 및 봉인 경로 거부
- 일별 횡단면 rank, Train-only 시장상태 변환, label 시점 검증
- 같은 입력 재실행 byte determinism
- 전체 회귀 테스트 통과

## Codex Handoff

- 구현 패키지: `src/kospi100_multifactor/`
- 파티션 builder: `src/kospi100_data/phase4b_partition.py`
- 설정: `configs/phase4b_multifactor.json`
- 실행: `PYTHONPATH=src python -m kospi100_multifactor.cli analyze --config configs/phase4b_multifactor.json --output artifacts/phase4b_multifactor`
- 완료 조건: 사전등록 hash 일치, 허용 파티션만 로드, 감사·manifest 생성, 관련 및 전체 테스트 통과
