# v2 Phase 4B — Agent D2 이중 결합 구조 명세

## 상태

- Experiment ID: `EXP-20260826-007`
- 상태: 결과 확인 전 사전등록
- 기간: 2019-01-02~2023-12-28 소비된 v2 개발자료 진단
- 승격 효력: 없음. 독립 OOS 또는 실거래 근거가 아니다.

## 연구 질문

Agent B2와 Agent C2를 다음 두 방식으로 결합했을 때 C2 단독보다 비용 차감 공식 KOSPI 200 초과수익과 위험 안정성이 개선되는가.

1. `B2_TOP80_SERIAL`: B2의 PIT Top 80을 먼저 고른 뒤 그 안에서만 C2가 진입 순위를 정한다.
2. `B2_RISK_CALIBRATION`: C2 전체 유니버스를 유지하고 B2를 제거 gate가 아닌 순위 보정값으로만 쓴다.

대조군은 `C2_ONLY_CONTROL`이다.

## 입력과 물리 경계

- B2: `EXP-20260826-005`의 hash 검증된 일별 점수
- C2: `EXP-20260826-006`의 hash 검증된 일별 점수
- PIT KOSPI 200 membership과 2019~2023 KRX 일봉
- 공식 KRX KOSPI 200 지수 코드 1028
- B2/C2 점수 파일은 각 manifest의 SHA-256과 일치할 때만 읽는다.
- v1 Development Test 파티션과 Final OOS는 접근하지 않는다.

## 고정 결합식과 매매 규칙

- Serial: B2 `broad_quality_eligible=true`만 남기고 C2 percentile 내림차순
- Calibration: `C2 percentile × (0.5 + 0.5 × B2 percentile)`
- B2가 없는 Calibration 종목은 B2 percentile 0으로 보정하되 제거하지 않는다.
- C2 원점수 0.05 이상, 결정순위 일별 상위 5개만 신규 진입 후보
- 결정순위 1~2위 11%, 3~5위 5%, 최대 보유 10종목, 피라미딩 금지
- t일 종가 신호, t+1 시가 주문, 절대 gap 5% 초과 시 주문 취소
- 손절 5%, 익절 10%, 최대 10세션, 같은 봉 충돌 시 `STOP_FIRST`
- 기존 수수료·세금표와 매수·매도 각 10bp slippage 사용

## 선택과 gate

후보 선택은 순초과수익률, Sharpe, 후보명 순으로 결정한다. 선택 후보는 모두 다음을 만족해야 진단상 수용한다.

- 공식 KOSPI 200 대비 연결 순초과수익률 > 0
- 연도별 양의 초과수익 3/5 이상
- Sharpe > 0
- MDD > -30%
- 원장 reconciliation PASS

결과가 좋아도 소비된 개발자료 진단이므로 거래 모델로 승격하지 않는다. 결과를 보고 결합식·임계값·보유규칙을 변경하지 않는다.

## 산출물

- `artifacts/v2_phase4b_agent_d2_release/`
- `candidate_metrics.csv`, `data_audit.json`, `decision.json`, `manifest.json`
- 선택 후보의 체결·현금·포지션·성과·reconciliation 원장
- 독립 재실행 디렉터리와 byte 동일성 검사

## 테스트와 완료 조건

- Serial이 B2 Top 80 밖 종목을 제거하는지 확인
- Calibration이 C2 종목을 제거하지 않는지 확인
- 대조군 순서가 B2에 영향받지 않는지 확인
- t 신호→t+1 시가, rank 비중, gap veto 확인
- 공식 지수 및 상류 hash 검증
- 세 후보 reconciliation PASS
- 독립 재실행 byte 동일
- D2 전용 및 전체 회귀 테스트 통과

## Codex Handoff

`src/kospi200_agent_d2/`, `configs/v2_phase4b_agent_d2.json`, D2 테스트를 구현한다. 실행 전 registry에 source/config/B2/C2/index hash를 동결하고, 실행 뒤에만 `docs/stages/v2_phase_4b_report.md`를 작성한다. 보호 OOS·v1 Development Test 접근, 기존 B2/C2 재학습, 결과 기반 재조정은 금지한다.
