# v2 Phase 2B Agent B 품질·하방위험 재설계 명세

## 상태

`COMPLETED_DIAGNOSTIC_ONLY`

Experiment ID는 `EXP-20260826-005`다. 기존 Agent B의 63세션 단순 종목수익 순위가 10세션 Agent D와 결합될 때 성과를 악화시킨 원인을 반영한다.

## 연구 질문

확정 재무제표 20개 Factor와 기계적 희석도를 사용해 향후 63세션 공식 KOSPI 200 초과수익에서 하방위험을 차감한 품질을 예측하면, 단순 미래수익 순위보다 안정적인 펀더멘털 후보군을 만들 수 있는가.

## 고정 계약

- Universe: 날짜별 실제 PIT KOSPI 200, 시가총액 상위 최대 200
- 입력: 확정 재무제표 20개 Factor percentile과 기계적 분할을 제외한 252세션 희석도
- benchmark: KRX 지수코드 1028 공식 KOSPI 200
- target: `63세션 종목수익률 - 63세션 KOSPI200 수익률 - 0.5 × 최대불리변동`
- 시점: t월 마지막 거래일 종가 뒤 계산, 다음 거래일부터 사용
- 모델: 고정 Ridge와 shallow HistGradientBoosting
- 평가: 연도별 expanding walk-forward 2019~2023, purge 63·embargo 63
- 출력: 전체 점수, 광범위 품질후보 Top80, 보고용 Top30
- Agent B는 직접 주문하거나 포트폴리오 백테스트를 하지 않는다.

동일 기간 결과를 본 뒤 penalty·Top80·모델·기간을 바꾸지 않는다. 2019~2023은 이미 소비된 개발 진단이며 독립 OOS로 부르지 않는다. v1 Development Test와 Final OOS에는 접근하지 않는다.

## 완료 조건

- 공식 지수 hash 및 index_code 1028 검증
- t+1~t+64 target과 하방위험 시점 테스트
- purge·embargo 및 Train-only 전처리 테스트
- 전체 점수와 Top80/Top30 결정성 검증
- 본 실행과 독립 재실행 byte determinism
- 전체 회귀 테스트 통과

## Codex Handoff

Phase 2B 결과를 확인한 뒤에만 Agent C2를 실행한다. Agent C2는 Agent B Top80에 직렬 종속시키지 않고 독립 기술 점수를 만들며, 후속 Agent D에서 B를 필터 또는 위험 calibration으로 비교한다.
