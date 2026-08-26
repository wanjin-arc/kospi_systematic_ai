# v2 Phase 3D — Agent C3 LSTM·CNN 실행 보고서

## 결론

Agent C를 실제 PyTorch LSTM·1D CNN으로 전면 재설계했다. `EXP-20260826-008`의 C3는 기존 C2보다 공식 KOSPI200 초과수익 Rank IC와 2:1 성공 AUC가 모두 개선됐다. 다만 2019~2023은 소비된 개발기간이므로 독립 OOS 또는 거래 승격 근거는 아니다.

## 구조

- LSTM: t일까지 40거래일 OHLCV 6채널로 t+1~t+10 실현 변동성 예측
- CNN: 같은 sequence로 t+1 시가 진입 후 +10%가 -5%보다 먼저 도달할 확률 예측
- 최종점수: `CNN 확률 - 0.5 × LSTM 예측변동성 일별 percentile`
- 위험가중치 0.5는 2017~2018 Train-only calibration의 네 후보 중 선택
- PyTorch 2.13.0 CPU, 고정 seed·결정성 알고리즘

## 결과

| 지표 | C2 | C3 |
|---|---:|---:|
| 평균 공식지수 초과수익 Rank IC | 0.04184 | 0.04776 |
| 2:1 성공 AUC | 0.51651 | 0.66410 |
| 양의 IC 연도 | 5/5 | 5/5 |

C3 연도별 IC는 2019 0.01768, 2020 0.02488, 2021 0.10526, 2022 0.04771, 2023 0.04275다.

## 감사

- membership: 989,568행
- 시장 파일: 4,945개 세션
- 학습 sequence: 71,491개
- 초기 적합 sequence: 61,496개
- calibration sequence: 9,599개
- 일별 점수: 242,716행
- calibration 적합 cutoff: 2016-12-01
- purge 10·embargo 10
- 본 실행과 독립 재실행 6개 파일 byte-identical
- Agent B·재무·포트폴리오 접근 없음
- v1 Development Test 물리 파티션·Final OOS 접근 없음

## 한계

CNN은 미래 장중 저점을 직접 예측하지 않는다. 과거 일봉 패턴으로 향후 10세션 2:1 성공 가능성을 분류한다. 실제 장중 저점·진입시점 모델에는 별도의 PIT 분봉이 필요하다.

## 산출물

- `src/kospi200_agent_c3/`
- `configs/v2_phase3d_agent_c3_lstm_cnn.json`
- `artifacts/v2_phase3d_agent_c3_lstm_cnn_release/`
- `artifacts/v2_phase3d_agent_c3_lstm_cnn_release_reproduction/`

## Codex Handoff

C3는 기술 점수 연구 입력으로 보존한다. 동일 2019~2023에서 구조·epoch·가중치를 재조정하지 않는다. 포트폴리오 평가는 별도 D3 결과를 따른다.
