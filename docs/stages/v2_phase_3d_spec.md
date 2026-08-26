# v2 Phase 3D — Agent C3 LSTM·CNN 전면 재설계 명세

## 상태

- Experiment ID: `EXP-20260826-008`
- 상태: 결과 확인 전 사전등록 완료
- 증거 지위: 2004~2023 소비된 개발기간 진단 전용

## 수정 대상 판단

Agent D2에서 B2를 추가하면 C2 단독보다 손실과 MDD가 줄었지만 공식 지수를 넘지 못했다. 따라서 우선 수정 대상은 펀더멘털 Agent B가 아니라 기술 점수의 방향성과 시계열 표현력이 부족한 Agent C다. B2는 변경하지 않고 후속 위험보정 입력으로 보존한다.

## 모델

### LSTM 변동성 분기

- 입력: t일까지의 40거래일 OHLCV causal sequence 6채널
- target: t+1~t+10의 연율화 실현 변동성
- 구조: 1층 LSTM, hidden 16, Smooth L1
- 역할: 예측 변동성이 높은 종목을 일별 percentile로 감점

### CNN 저점·2:1 성공 분기

- 입력: 같은 40거래일 sequence
- target: t+1 시가 진입 후 10세션 안에 +10%가 -5%보다 먼저 도달했는지
- 같은 일봉에서 양쪽 barrier가 모두 닿으면 실패로 처리하는 STOP_FIRST 계약을 상류 label에서 계승
- 구조: 1D Conv 2층, BCEWithLogits

CNN은 미래 장중 저점을 직접 아는 모델이 아니다. t일까지 완성된 일봉 패턴이 향후 2:1 거래에 유리한지를 확률화한다.

## 결합과 기간

- 기본 적합: 2004~2016
- Train-only calibration: 2017~2018
- 점수 진단: 2019~2023
- 최종 점수: `CNN 성공확률 - λ × LSTM 예측변동성 일별 percentile`
- λ 후보: 0, 0.25, 0.5, 0.75
- λ 선택: 2017~2018 평균 일별 공식 KOSPI200 비용 차감 초과수익 Rank IC, 동률 시 AUC, 작은 λ
- calibration 후 모델은 2018년 이하 전체로 재적합하고 2019년 이후를 점수화

## 데이터 경계

- PIT KOSPI 200 membership
- 2004~2023 KRX OHLCV와 공식 KRX 지수 코드 1028
- sequence는 membership 공백·거래소 세션 공백·mechanical reset을 넘지 않는다.
- Agent B·재무·포트폴리오 접근 금지
- v1 Development Test 물리 파티션과 Final OOS 접근 금지

## 고정 학습값

- PyTorch 2.13.0, seed 20260826, CPU 결정성 알고리즘
- lookback 40, horizon 10, Train 표본 간격 10세션
- LSTM hidden 16, CNN channel 16, epoch 6, batch 1024
- AdamW learning rate 0.001, weight decay 0.0001
- 결과를 보고 epoch·구조·λ 후보·기간을 변경하지 않는다.

## 완료 조건

- 실제 `nn.LSTM`·`nn.Conv1d` 사용 확인
- 미래 bar 변경이 과거 sequence를 바꾸지 않음
- membership gap·mechanical reset 경계 확인
- 작은 학습의 byte-level tensor 결정성
- t+1 진입·2:1 STOP_FIRST label 회귀 유지
- 실제 실행과 독립 재실행 산출물 byte 동일
- 전체 회귀 테스트 통과

## 비목표

- 분봉 최저점 예측
- Agent B 재학습
- 결과 기반 임계값 탐색
- 독립 OOS 또는 거래 승격
- 포트폴리오 백테스트

## Codex Handoff

`src/kospi200_agent_c3/`, 동결 설정, 테스트를 구현하고 실행 전 registry에 코드·설정·데이터·PyTorch 버전을 고정한다. C3가 유효한 점수를 만들면 별도 D3 Experiment에서만 0.05/0.075 비중과 2:1 시가 매매를 평가한다.
