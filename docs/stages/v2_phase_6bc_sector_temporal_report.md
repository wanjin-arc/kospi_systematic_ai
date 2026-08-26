# v2 Agent B4·C5 섹터·시계열 재설계 실행 보고서

## 실행 경계

- Agent B4: `EXP-20260826-015`
- Agent C5: `EXP-20260826-016`
- 2004~2023은 이미 소비된 개발자료이며 결과는 내부 진단이다.
- Final OOS, v1 전용 Development Test 파티션, 포트폴리오 backtest, 실제 주문은 접근하지 않았다.
- 원 실행과 독립 재실행의 모든 산출물이 byte-identical했다.

## Agent B4 결과

입력은 264,341행·248종목·22업종의 섹터 병합 펀더멘털 패널이다. 20개 팩터에 시장/섹터 percentile과 robust z, 1·3개월 섹터 z 변화량, 희석도 percentile을 더해 총 121개 Feature를 사용했다. 섹터 누락은 0행이다.

| 모델 | 평균 Rank IC | NDCG@80 | 양수 연도 |
|---|---:|---:|---:|
| 기존 B2 Ridge | 0.03284 | 0.65654 | 3/5 |
| B4 Ridge sector-temporal | 0.03186 | 0.65604 | 3/5 |
| B4 shallow HistGB | 0.01028 | 0.64761 | 3/5 |
| B3 XGBRanker | -0.00253 | 별도 NDCG@30 | 1/5 |

B4 Ridge는 B3보다 낫지만 기존 B2보다 평균 Rank IC와 NDCG가 모두 소폭 낮다. 섹터 정규화는 구조적 업종 편향을 줄이는 감사·해석 장점은 있으나, 현재 target에서 추가 예측력을 만들지는 못했다. B4는 B2 대체 후보로 기각한다.

## Agent C5 결과

C5는 재무·Agent B를 전혀 읽지 않았다. 기존 C3의 6개 OHLCV sequence에 20일 낙폭, 20일 저점 거리, 5/20일 범위 압축, 20일 실현변동성을 추가했다. LSTM은 10세션 변동성을, CNN은 5% 손절보다 10% 익절이 먼저 발생할 확률을 학습했다.

| 지표 | 기존 C3 | C5 | 판단 |
|---|---:|---:|---|
| 평균 초과수익 Rank IC | 0.04776 | -0.01307 | 크게 악화 |
| 양수 IC 연도 | 5/5 | 2/5 | 악화 |
| CNN bottom AUC | 0.66410 | 0.66558 | 미세 개선 |
| LSTM 변동성 MAE | 0.11757 | 0.11708 | 미세 개선 |
| calibration 선택 risk weight | 0.50 | 0.25 | 참고 |

연도별 C5 IC는 2019 `0.00261`, 2020 `0.02616`, 2021 `-0.05052`, 2022 `-0.01237`, 2023 `-0.03220`이다. CNN과 LSTM의 개별 보조과제는 조금 좋아졌지만 결합 점수는 미래 초과수익 순위와 반대 방향이 됐다. “저점 성공확률”과 “낮은 변동성”이 곧바로 높은 시장초과수익을 뜻하지 않는다는 증거다. C5는 C3 대체 후보로 기각한다.

## 결론

- Agent B 유지 기준: 기존 B2 Ridge. B4는 해석·감사용 연구 산출물로 보존한다.
- Agent C 유지 기준: 기존 C3 LSTM 변동성 + CNN 2:1 성공 모델. C5는 사용하지 않는다.
- B4와 C5를 결합한 Agent D 실험은 수행하지 않는다. 입력 Agent가 각각 기존 기준을 개선하지 못했기 때문이다.
- 이 결과를 보고 가중치·lookback·target·모델 크기를 다시 조정하지 않는다. 추가 연구는 새 Experiment와 새 forward 자료가 필요하다.

## 산출물

- `artifacts/v2_agent_b4_sector_temporal/`
- `artifacts/v2_agent_b4_sector_temporal_reproduction/`
- `artifacts/v2_agent_c5_lstm_cnn_path/`
- `artifacts/v2_agent_c5_lstm_cnn_path_reproduction/`

## Codex Handoff

두 실험은 내부 개발 진단으로 종료됐다. 기존 B2·C3 결과와 코드는 변경하지 않았다. 다음 단계에서 사용할 수 있는 연구 기준은 B2와 C3이지만 거래 후보 승격은 아니며, 포트폴리오·Agent D·Final OOS 실행 권한을 부여하지 않는다.
