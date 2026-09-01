# v2 Phase 6 Agent B3 실행 보고서

## 실행 정보

- Experiment ID: `EXP-20260826-014`
- 모델: `XGBRanker`, `objective=rank:ndcg`
- XGBoost: `3.4.1`
- 입력: 표준 펀더멘털 Factor 패널 264,341행, 2016-03-24~2023-12-28
- legacy 저커버리지 재무 패널: 0행
- 가격 입력: KRX market_stk 1,966개 파일
- 공식 지수: KRX 1028, 4,945행
- 포트폴리오 backtest: 실행하지 않음
- Final OOS: 접근하지 않음

## 결과

| Validation 연도 | Train 종료 | Rank IC | NDCG@30 |
|---:|---|---:|---:|
| 2019 | 2018-07-25 | -0.08024 | 0.49934 |
| 2020 | 2019-07-24 | -0.00067 | 0.55791 |
| 2021 | 2020-07-24 | -0.05615 | 0.53175 |
| 2022 | 2021-07-26 | 0.12609 | 0.57981 |
| 2023 | 2022-07-26 | -0.00168 | 0.54483 |

양의 Rank IC 연도는 1/5개이며 평균 Rank IC는 약 -0.00253이다. 기존 Ridge 기반 B2의 평균 Rank IC 0.03284, 양의 연도 3/5보다 개선되지 않았다.

## 기술적 수정

XGBoost `rank:ndcg`는 기본 exponential gain에서 relevance를 31 이하 정수로 제한한다. 날짜별 경제 target을 훼손하지 않기 위해 날짜별 순위를 0부터 시작하는 정수 relevance로 변환하고 `ndcg_exp_gain=false`를 고정했다. 날짜별 query group, seed, CPU 단일 스레드와 모델 설정은 실행 전에 고정됐다.

## 결정

XGBRanker 구현·실행은 성공했지만, 기존 B2 Ridge의 대체 모델로 채택하지 않는다. B3 산출물은 재현 가능한 연구 후보로 보존하고, D에 연결하거나 미래 shadow 모델로 승격하지 않는다. B2의 기존 결과와 판정은 변경하지 않는다.

## 산출물

- `artifacts/v2_phase6_agent_b_xgbranker/fold_metrics.csv`
- `artifacts/v2_phase6_agent_b_xgbranker/daily_agent_b3_scores.csv.gz`
- `artifacts/v2_phase6_agent_b_xgbranker/selected_model.json`
- `artifacts/v2_phase6_agent_b_xgbranker/data_audit.json`
- `artifacts/v2_phase6_agent_b_xgbranker/manifest.json`

주요 입력 hash:

- config: `2ce47a10aab00a517a66ca0f7ed3cd2dbe89bb38e1cff7573141407f1410d632`
- factor panel: `0ba2cb148b7e076d221a62b8b323ff18063518700b1dd597c5005ac46a0ab857`
- market tree: `f1569410c224887bff8a67b25af959d0fca05419ac1e7c47005a391688b372e6`
- official index: `64a078ffc087bcb669f253800ac1e7c98521fe2654132d9cbb706726b1a8623b`

## Codex Handoff

B3는 기술적으로 사용 가능하지만 예측 후보로는 기각됐다. 다음 단계에서 B를 사용해야 한다면 기존 B2 Ridge를 보존 후보로 사용하고, B3를 결과 확인 후 재튜닝하지 않는다. XGBoost 버전과 B3 hash는 재현용으로만 동결한다.
