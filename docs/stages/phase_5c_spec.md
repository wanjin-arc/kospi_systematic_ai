# Phase 5C 점수 지속성·저회전율 Ranking 명세

## 1. 상태와 연구 성격

- Experiment ID: `EXP-20260823-003`
- 상태: 사전등록, 구현 및 2015~2018 적응적 진단 허용
- Development Test: 미승인, 로드·계산·평가·선택 금지
- Final OOS: 봉인 유지

Phase 5C는 Phase 5B 결과를 본 뒤 시작한 적응적 엔지니어링 실험이다. 따라서 2015~2018 결과가 좋아도 독립적인 채택 증거가 아니며, 거래 후보 또는 Development Test 후보로 자동 승격하지 않는다.

## 2. 문제 정의

Phase 5B의 진단상 최선 모델 `elastic_a005_l02`는 일별 종목 점수를 만들었지만 연결 순초과수익률 -11.5013%p, turnover 157.8263배, 평균 현금 20.0849%, 명시적 비용 2,430,466.36원이었다. 매일 변하는 미세한 순위에 따라 10일마다 교체하고, 상위 주문이 미체결되거나 이미 보유 중이면 후순위 종목으로 현금을 채우지 못한 구조가 신호의 약한 우위를 소모했을 가능성을 검증한다.

## 3. 고정 신호와 변경 범위

다음은 변경하지 않는다.

- Phase 4B의 21개 종목변수, 5개 시장상태, 6개 상호작용
- `t` 종가까지 계산하는 일별 종목 점수
- `t+1` 시가 이후 체결
- `elastic_a005_l02` 모델과 각 fold Train-only 적합
- D09 target, purge 20, embargo 20
- 500만원, long-only, 최대 10종목, 종목당 10%, no pyramiding
- 비용·세금·10bp adverse slippage와 2배·3배 stress

Phase 5C에서 한 번만 사전등록해 변경하는 것은 점수와 주문의 시간적 지속성이다.

1. 같은 fold·membership spell·연속 거래세션 안에서만 과거 포함 5세션 EMA로 점수를 평활한다.
2. 평활 점수를 매일 KOSPI 100 적격 종목 안에서 다시 순위화한다.
3. 목표 진입은 상위 10개다. 기존 보유·고가·gap 미체결로 자리가 남으면 순위 20위까지만 결정적 fallback 주문을 제출한다.
4. 보유 종목은 순위 20위 밖으로 밀리면 다음 거래일 시가에 청산한다.
5. 안전 상한으로 20세션이 되면 청산한다.

## 4. 데이터 독립성과 Phase 명칭

Phase 이름은 이미 본 데이터를 다시 미사용 데이터로 만들지 않는다. Phase 5의 2019~2021과 Phase 5B/5C의 2015~2018은 이미 연구 과정에서 소비됐다. Phase 5C 연구 runner는 `data/processed/v24/phase4b_train_internal_2018/`만 읽고 최대 입력일 2018-12-31을 reader 호출 전에 검증한다.

2022~2023은 이번 단계에서 열지 않는다. 향후 한 개 정책을 완전히 동결한 뒤 사용자 별도 승인이 있어야 모델별 제한된 확인 구간으로 한 번 사용할 수 있다. Phase 3에서 이미 프로젝트 수준으로 관찰됐으므로 이를 완전한 전역 OOS라고 부르지 않는다.

## 5. Gate 해석

4개 연도에서 “80% 이상 비음수”는 정수 반올림 때문에 사실상 4/4가 되어 표본이 작은 상태에서 과도한 기각을 만들 수 있다. 그러나 실패 결과를 본 뒤 기존 D20을 소급 완화하는 것도 적응적 과최적화다. 따라서 이번 실험은 D20을 변경하거나 통과시키지 않는다.

적응적 진단 통과 조건은 Phase 5B 동일 신호·동일 구간 대비 다음을 모두 만족하는 것이다.

- turnover 40% 이상 감소
- 명시적 비용 30% 이상 감소
- 평균 현금 비중 10% 이하
- 연결 순초과수익률 개선
- MDD 악화가 5%p 이내

이는 주문 구조가 의도대로 개선됐는지를 보는 진단 gate이며 거래 채택 gate가 아니다. 미래 확인용 권고 gate는 연결 기본비용 순초과수익률 양수, 2배 비용 순초과수익률 비음수, Sharpe 양수, 최악 연도 순초과수익률 -15%p 이상이다. 연도별 양수 비율은 보고하되 hard gate로 사용하지 않는다. 이 권고는 별도 사용자 승인 전 D20을 대체하지 않는다.

## 6. 분봉 데이터

분봉은 이번 일봉 Ranker 학습에 사용하지 않는다. 가용기간과 결측 구조가 장기 일봉 표본과 다르고, 지금 섞으면 최근 기간 선택편향과 표본 축소가 생긴다. 일봉 순위·포트폴리오 정책이 독립 확인을 통과한 뒤, 동일 coverage 표본에서 다음 날 시가 즉시 진입 대비 5분·15분 Entry Timing 개선만 별도 단계에서 평가한다.

## 7. 산출물

- `artifacts/phase5c/adaptive_diagnostic/portfolio_metrics.csv`
- `artifacts/phase5c/adaptive_diagnostic/fold_rank_metrics.csv`
- `artifacts/phase5c/adaptive_diagnostic/fold_audit.csv`
- `artifacts/phase5c/adaptive_diagnostic/policy_audit.json`
- `artifacts/phase5c/adaptive_diagnostic/engineering_decision.json`
- `artifacts/phase5c/adaptive_diagnostic/score_contract.json`
- `artifacts/phase5c/adaptive_diagnostic/data_audit.json`
- `artifacts/phase5c/adaptive_diagnostic/run.json`
- `artifacts/phase5c/adaptive_diagnostic/manifest.json`

## 8. 테스트와 완료 조건

- 설정·Experiment ID·고정 후보·물리 입력 최대일 guard
- Development Test 및 금지 경로 fail-closed
- EMA가 현재와 과거 점수만 사용하고 fold·spell·세션 gap에서 reset되는지 검증
- `t` 점수에서 `t+1` 주문만 생성되는지 검증
- 상위 10 목표·20위 fallback·20위 이탈 청산·20세션 상한 검증
- 동일 입력 byte determinism
- Phase 0~5B 전체 회귀 유지

실행 전 registry의 source/config/data/model hash를 동결한다. 실제 실행 후에만 보고서를 작성한다. Development Test 명령은 구현하지 않거나 항상 거부한다.

## Codex Handoff

- 구현: `src/kospi100_rank_persistence/`
- 설정: `configs/phase5c_persistent_ranking.json`
- 테스트: `tests/test_phase5c_config.py`, `tests/test_phase5c_policy.py`
- 실행: `PYTHONPATH=src python -m kospi100_rank_persistence.cli run --config configs/phase5c_persistent_ranking.json --output artifacts/phase5c/adaptive_diagnostic`
- 완료: 해시 동결, 2018년 이하 입력만 사용, 진단 산출물·감사·manifest 생성, 관련 및 전체 테스트 통과, 독립 재실행 byte 일치
