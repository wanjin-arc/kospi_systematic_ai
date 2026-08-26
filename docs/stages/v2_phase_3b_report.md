# v2 Phase 3B 독립 Technical Agent C 보고서

## 구조 결론

Agent B가 Top 30을 먼저 제한하는 직렬 구조보다 Agent B와 Agent C를 독립 생성하고
Agent D가 결합하는 구조가 현재 증거에서는 더 낫다.

- 직렬 Agent C 평균 Rank IC: -0.0072
- 독립 Agent C 평균 Rank IC: +0.0347
- 독립 Agent C 연도별 양수 IC: 5/5
- Agent B·독립 Agent C 점수 평균 일별 Spearman: -0.0523

낮은 음의 상관은 두 Agent가 거의 같은 정보를 반복하지 않음을 뜻한다. 다만 아직 Agent D
결합 성과나 포트폴리오 수익을 확인한 것은 아니다.

## 구현 구조

Agent B·재무 데이터를 전혀 읽지 않고 전체 PIT KOSPI 200 OHLCV만 사용했다.

- risk branch: 향후 10세션 최대 불리 변동률 예측
- bottom branch: +10% 익절이 -5% 손절보다 먼저 발생할 확률 예측
- 같은 날 손절·익절 동시 도달: 손절 우선
- 10세션 후 자동 종료와 40bp 비용 proxy
- t+1 시가 gap 절대 5% 초과: 향후 Agent D 실행 veto 정보

현재 Python 3.14 환경에는 PyTorch·TensorFlow·Keras가 없어 실제 LSTM/CNN은 실행하지
않았다. Ridge/Logistic과 shallow HistGradientBoosting으로 두 분기 구조의 선행 가설을 검증했다.

## 결과

| 모델 | 평균 composite Rank IC | bottom AUC | risk MAE |
|---|---:|---:|---:|
| hist event dual | 0.0347 | 0.6359 | 0.0352 |
| linear event dual | 0.0264 | 0.6401 | 0.0353 |

hist 모델의 연도별 IC는 2019 0.0380, 2020 0.0388, 2021 0.0257,
2022 0.0302, 2023 0.0408로 모두 양수였다. 사전등록 우선순위에 따라
`hist_event_dual`을 Agent D 입력 후보로 선택했다.

## 데이터·감사

- PIT membership: 295,924행, 1,477일, 일별 200~202개
- 모델 표본: 58,514행
- 일별 Agent C 점수: 243,829행
- 기계적 reset: 26건
- Agent B 접근: 없음
- 펀더멘털 접근: 없음
- v2 2022~2023 consumed development: 실제 로드
- v1 Development Test·Final OOS: 접근하지 않음
- 포트폴리오 백테스트: 없음
- 독립 재실행 5개 산출물: byte-identical
- Phase 3B 전용 테스트: 3/3 통과
- 전체 회귀 테스트: 195/195 통과

## 산출물

- `artifacts/v2_phase3b_independent_agent_c_release/fold_metrics.csv`
- `artifacts/v2_phase3b_independent_agent_c_release/model_summary.csv`
- `artifacts/v2_phase3b_independent_agent_c_release/daily_independent_agent_c_scores.csv.gz`
- `artifacts/v2_phase3b_independent_agent_c_release/selected_model.json`
- `artifacts/v2_phase3b_independent_agent_c_release/data_audit.json`
- `artifacts/v2_phase3b_independent_agent_c_release/manifest.json`

## Codex Handoff

다음 단계는 Agent D 사전등록이다. Agent B와 C의 점수를 결과 확인 후 임의 가중하지 말고,
고정 후보 가중치·no-trade·gap veto·최대 보유·비중·2:1 청산 규칙을 새 Experiment ID로
먼저 동결한다. Agent C 단독 결과를 거래 승인으로 해석하지 않는다.
