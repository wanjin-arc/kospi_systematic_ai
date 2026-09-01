# Phase 5E 절대 알파·No-Trade 모델 명세

## 1. 승인과 연구 질문

- Experiment ID: `EXP-20260823-005`
- 사용자 승인: 2026-08-23, 제안된 Phase 5E 진행 승인
- 상태: 사전등록 후 adaptive diagnostic
- Development Test: 미승인·미접근
- Final OOS: Phase 8까지 봉인

연구 질문은 `t`일 종가까지의 기술적 정보로 `t+1` 시가 진입부터 `t+11` 시가 청산까지 거래비용을 차감하고도 KOSPI 100보다 높은 수익을 낼 종목을 식별할 수 있는가이다. Phase 5D의 일별 z-score는 횡단면 상대값이라 매일 후보를 만들었다. Phase 5E는 절대 예상 순초과수익과 그 값이 양수일 확률을 직접 추정한다.

2019~2021은 이미 여러 Phase에서 확인한 구간이므로 Test 또는 OOS가 아니다. 이번 결과는 구현·원인 진단용이며 좋아도 거래 후보로 승격하지 않는다.

## 2. 입력과 Feature

- 물리 입력: `data/processed/v24/phase5_train_validation_2021/`
- 입력 역할: `phase5_train_validation`
- 물리 최대일: `2021-12-31`
- 종목 Feature: Phase 4B의 21개 기술변수 일별 횡단면 rank
- 시장 Feature: KOSPI 100과 동시점 Breadth 기반 5개 변수
- 상호작용: Phase 4B에 등록된 6개
- 시장상태 Feature는 모델 입력으로만 사용하고 보유 수를 강제로 10·5·0으로 바꾸지 않는다.

Feature는 `t`일 공식 장 종료까지 계산하고 주문은 `t+1` 이후에만 실행한다. Point-in-Time membership, `rank_eligible`, `tradable`, Corporate Action reset 경계를 유지한다.

## 3. Target

종목 `i`, 신호일 `t`의 비용 전 초과 로그수익률은 다음과 같다.

```text
gross_excess = log(stock_open[t+11] / stock_open[t+1])
             - log(index_open[t+11] / index_open[t+1])
```

비용 조정은 기본 commission 2bp/side, adverse slippage 10bp/side, `t+11`의 법정 매도세율을 사용한다. 회귀 target은 이 비용을 로그수익에서 차감한 `net_excess`이고 분류 target은 `net_excess > 0`이다. 횡단면 rank 변환은 하지 않는다.

## 4. 모델과 전처리

- 회귀: Ridge, `alpha=100`
- 분류: Logistic Regression, `C=1`, `max_iter=5000`
- 후보 탐색·결과 기반 모델 선택: 없음
- 결측 대체와 시장변수 표준화: 각 fold Train에서만 적합
- purge: 20거래일
- embargo: 20거래일
- Random split: 금지

Anchored fold는 2011~2018→2019, 2011~2019→2020, 2011~2020→2021이다.

## 5. 점수·매매·현금 규칙

- 일별 점수: 회귀 모델의 예상 순초과수익
- 신규매수: 예상 순초과수익 `>=0.005`이고 양수 확률 `>=0.60`
- 후보 순위: 위 조건 통과 종목을 예상 순초과수익 내림차순, 동률이면 `security_id` 오름차순
- 일별 최대 제출 후보: 10
- 통과 종목이 없으면: 주문하지 않고 현금 유지
- 청산: 예상 순초과수익 `<=0`, 양수 확률 `<0.50`, membership/tradable 강제조건, 또는 최대 10세션
- 최대 보유: 10종목
- 최소 보유: 0종목
- 종목당 목표비중: 10%
- 피라미딩·공매도·레버리지: 금지
- 평균 현금: 보고 지표이며 hard gate가 아님

## 6. 경제성 진단 gate

무결성 gate는 미래정보·PIT·물리 입력 경계·비용·원장 조정·결정성을 필수로 한다. 성과 진단은 다음을 계산한다.

- 기본비용 연결 순초과수익률 `>0`
- 2배 비용 연결 순초과수익률 `>=0`
- 진입 주문 100건 이상
- 전략 MDD가 지수 MDD보다 5%p 넘게 악화되지 않음

연도별 양수 비율, 평균 현금, 최소 보유 수는 hard gate가 아니다. 다만 2019~2021이 이미 소비됐으므로 위 조건을 모두 만족해도 자동 승격하지 않는다. 기존 D20은 변경하지 않는다.

## 7. 데이터 경계와 감사

- 2022~2023 loaded/calculated/evaluated/selected는 모두 0이어야 한다.
- Final OOS 경로는 코드·설정·명령에 포함하지 않는다.
- 파티션·manifest·파일 hash·날짜 경계를 데이터 reader 전에 검증한다.
- 로드 후 날짜 필터링은 금지한다.
- source/config/data/model hash를 실제 실행 전에 registry에 동결한다.

## 8. 산출물

- `model_metrics.csv`
- `fold_audit.csv`
- `portfolio_metrics.csv`
- `signal_activity.csv`
- `no_trade_audit.json`
- `diagnostic_decision.json`
- `target_contract.json`
- `data_audit.json`
- `run.json`
- `manifest.json`

실제 실행 결과를 확인한 뒤에만 `docs/stages/phase_5e_report.md`를 작성한다.

## 9. 테스트와 완료 조건

- 설정 버전·Experiment ID·target·threshold·모델 고정 검증
- Development Test와 금지 경로 fail-closed
- `t` 신호→`t+1` entry→`t+11` exit와 비용 조정 검증
- 횡단면 rank target 미사용 검증
- Train-only 전처리·Ridge·Logistic 적합과 purge/embargo 검증
- 양수 기대수익·확률 이중 gate, 0종목·현금 허용, 최대 10종목 검증
- 미래 예측 변경이 과거 주문을 바꾸지 않음
- 원장 조정, 비용 stress, 감사 필드, manifest hash, byte determinism
- Phase 0~5D 전체 회귀 테스트 통과

## Codex Handoff

- 구현: `src/kospi100_absolute_alpha/`
- 설정: `configs/phase5e_absolute_alpha.json`
- 테스트: `tests/test_phase5e_config.py`, `tests/test_phase5e_modeling.py`, `tests/test_phase5e_policy.py`
- 실행 전 hash 확인: `PYTHONPATH=src python -m kospi100_absolute_alpha.cli freeze --config configs/phase5e_absolute_alpha.json`
- 실행: `PYTHONPATH=src python -m kospi100_absolute_alpha.cli run --config configs/phase5e_absolute_alpha.json --output artifacts/phase5e/adaptive_diagnostic`
- 완료 후에도 Development Test와 Final OOS는 자동 실행하지 않는다.
