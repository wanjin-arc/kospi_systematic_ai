# v2 Phase 6E 시계열 Agent B·C·D 사전등록 명세

## 목적

재무 공시의 시점별 단면과 종목별 시계열 변화를 함께 반영한 Agent B5, 이미 독립된 OHLCV 전용 LSTM·CNN 구조를 재적합한 Agent C6, 그리고 B5의 Top 30을 선필터로 사용하는 직렬 Agent D7을 같은 개발 경계에서 진단한다.

## 입력과 경계

- Universe: 시점별 KOSPI 200 구성종목.
- Agent B5: PIT 재무 패널, 공식 KOSPI 200 지수, 시가총액·희석 감사 필드만 사용한다. OHLCV는 B의 입력 변수로 사용하지 않는다.
- Agent C6: OHLCV와 PIT 구성종목만 사용하며 재무 패널을 읽지 않는다.
- Agent D7: B5·C6의 고정 산출물, 구성종목·시가·공식 지수만 사용한다.
- 훈련·진단 범위는 2004~2023의 이미 소비된 개발자료다. 2019~2020에서 정책을 선택하고, 2021~2023은 소비된 개발 진단으로만 기록한다.
- 2024년 이후 자료와 `data/sealed/final_oos_v24/`는 열람·스캔·로드·집계하지 않는다.

## Agent B5

- 재무 21개 factor에 대해 시점별 단면 percentile과, 패널에 검증되어 존재하는 robust z-score를 사용한다. `dilution_252`는 기존 패널의 시간축 희석 감사 지표이므로 중복 robust-z를 합성하지 않는다.
- 같은 종목의 과거 63·252거래일 차이를 추가하되, `t`의 값에는 `t` 이후 자료를 절대 사용하지 않는다.
- `XGBRanker(rank:ndcg)`가 63거래일 비용 차감 초과수익 기반 품질 target의 종목별 순위를 학습한다.
- 매일 PIT 시가총액·희석 검증을 거친 200종목에서 상위 30개만 보고 후보로 기록한다. 포트폴리오 백테스트는 수행하지 않는다.

## Agent C6

- 기존 C3의 40세션 OHLCV 전용 LSTM(변동성)·CNN(저점 후 +10%가 -5%보다 먼저 도달할 확률) 구조를 같은 seed로 별도 재적합한다.
- 재무·업종·Agent B 변수는 사용하지 않는다. 이는 새 후보 탐색이 아니라 C3 구현의 독립된 입력·모델 해시 동결이다.

## Agent D7

- B5 `report_top30`을 하드 게이트로 적용한 뒤에만 C6 점수를 사용한다.
- B 순위 percentile과 C 점수 percentile을 B 가중치 0, 0.5, 1.0의 사전등록 grid로 결합한다.
- CNN 저점 확률이 0.55 이상이면 5%, 0.65 이상이면 11% 목표 비중으로 한다. 이 값은 C3의 원점수 0.05/0.075가 아니라 확률값이다.
- t 종가 신호, t+1 시가 체결, 5% gap veto, -5% 손절, +10% 익절, 최대 10세션, 동시 충돌 시 STOP_FIRST를 적용한다.

## 불변 조건과 판정

- 모든 변환·모델·정책 선택은 해당 시점보다 앞선 자료로만 적합한다.
- B5는 B2의 평균 Rank IC와 양(+) 연도 수를 비교한다. C6은 C3와 metric·model hash 재현성을 비교한다.
- D7은 2019~2020 선택 구간과 2021~2023 진단 구간을 분리 보고하며, 비용 차감 순초과수익률·Sharpe·MDD·turnover를 함께 기록한다.
- 어떤 결과도 독립 OOS 증거 또는 거래 승인으로 해석하지 않는다.

## 산출물·검증

- 설정·코드·입력·모델·산출물 SHA-256 manifest, 정책 선택표, 일별 점수와 체결 원장을 남긴다.
- 전용 테스트, 전체 회귀 테스트, 동일 입력 재실행의 byte determinism을 검증한다.

## Codex Handoff

- 구현: `src/kospi200_agent_b5/`, `src/kospi200_agent_d7/`, 기존 `src/kospi200_agent_c3/`.
- 설정: `configs/v2_agent_b5_temporal_xgbranker.json`, `configs/v2_agent_c6_lstm_cnn_refit.json`, `configs/v2_agent_d7_serial_b5_c6.json`.
- 실행은 registry에 `EXP-20260827-001`~`003`을 먼저 등록한 뒤에만 수행한다.
