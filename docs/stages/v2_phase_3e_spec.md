# v2 Phase 3E Agent C4 사전등록 명세

## 목적

Agent C3는 2:1 barrier 성공확률의 순위 진단은 개선했지만, 그 점수가 실제 10거래일 공식 KOSPI200 초과수익의 경제적 크기를 직접 나타내지 않았다. Agent C4는 40거래일 OHLCV 시퀀스에서 비용 차감 10거래일 공식지수 초과수익과 양의 초과수익 여부를 함께 학습한다.

## 동결 계약

- Experiment ID: `EXP-20260826-010`
- Universe: 날짜별 실제 KOSPI 200
- Train: 2004-03-02~2018-12-28
- Train 내부 calibration: 2017-01-02~2018-12-28, purge 10·embargo 10
- 소비된 개발 진단: 2019-01-02~2023-12-28
- 입력: 40세션 OHLCV 6채널만 사용하며 Agent B와 포트폴리오에는 접근하지 않는다.
- 모델: LSTM 경로 분기와 1D CNN 국소 패턴 분기의 공동 표현, 초과수익 회귀 head와 양수 여부 분류 head
- 점수: 일별 예상 초과수익 percentile + 0.25 × 양수확률 percentile
- Random split, Final OOS, v1 Development Test 접근 금지

## 출력과 완료 조건

`daily_agent_c4_scores.csv.gz`, calibration/evaluation, 동결 모델, 데이터 감사, hash manifest를 남긴다. 같은 설정 독립 재실행의 byte determinism과 전체 회귀 테스트를 확인한다. 이 단계의 ML 진단만으로 거래 후보로 승격하지 않는다.

## Codex Handoff

`src/kospi200_agent_c4/`, 동결 설정, 전용 테스트를 구현하고 registry 사전등록 이후 실행한다. 결과를 `docs/stages/v2_phase_3e_report.md`에 사실대로 기록한다.
