# v2 Agent B4·C5 섹터·시계열 재설계 명세

## 목적과 지위

이미 소비된 2004~2023 개발자료에서 Agent B와 Agent C의 구조를 각각 한 번 재설계한다. 이 결과는 내부 진단이며 독립 OOS 증거가 아니다. 2024~2025 봉인 자료, 실제 주문, 포트폴리오 backtest는 사용하지 않는다.

## Agent B4

- Experiment ID: `EXP-20260826-015`
- 입력: PIT KOSPI 200 펀더멘털·섹터 패널, KRX 1028 지수, 동일 날짜 시가총액·상장주식수
- 기간: 2016-03-24~2023-12-28, 2019~2023 연도별 anchored walk-forward
- target: t+1 시가~t+64 시가 공식 KOSPI 200 초과수익률에서 최대 불리 경로의 0.5배를 차감
- Feature: 20개 팩터의 시장 percentile·robust z, 섹터 percentile·robust z, 섹터 z의 1개월·3개월 과거 변화량, 252세션 희석도 percentile
- 후보: 고정 Ridge(alpha=10), 고정 shallow HistGradientBoosting
- purge/embargo: 각각 63세션
- 선택: 평균 일별 Rank IC, NDCG@80, 단순성 순서
- 출력: 일별 점수·순위·Top30, fold 지표, 모델·데이터 감사, hash manifest

## Agent C5

- Experiment ID: `EXP-20260826-016`
- Agent B·재무자료 접근: 금지
- 입력: PIT KOSPI 200 OHLCV·상장주식수와 공식 KRX 1028 지수
- 학습: 2004-03-02~2018-12-28, calibration 2017~2018, 진단 2019~2023
- 구조: LSTM은 향후 10세션 변동성, CNN은 5% 손절보다 10% 익절이 먼저 도달할 확률을 학습
- 경로 Feature: 갭, 장중 고저·종가 위치, 종가수익률, 거래량 z, 20일 낙폭·저점 거리·실현변동성, 5/20일 범위 압축
- 점수: `CNN 성공확률 - w × LSTM 예측변동성 횡단면 percentile`, `w ∈ {0, .25, .5, .75}`는 2017~2018에서만 선택
- purge/embargo: 각각 10세션
- 비교: 기존 C3와 동일한 기간·target·모델 크기·epoch를 유지하고 경로 Feature 추가 효과만 비교

## 금지사항과 완료 조건

- Final OOS, v1 Development Test 전용 파티션, 포트폴리오 backtest, Agent D, 실주문 접근 금지
- 결과 확인 후 후보·기간·target·가중치 grid 변경 금지
- 실행 전 registry와 코드·설정·데이터 hash 동결
- 관련 테스트와 전체 회귀 테스트 통과
- 실제 산출물·manifest·비교 보고서 생성

## Codex Handoff

구현 파일은 `src/kospi200_agent_b4/`, `src/kospi200_agent_c5/`, 두 설정과 전용 테스트다. 실행 명령은 각각 `python -m kospi200_agent_b4.cli run`과 `python -m kospi200_agent_c5.cli run`이다. 결과는 기존 B2/B3/C3/C4를 변경하지 않고 별도 artifacts에 쓴다.
