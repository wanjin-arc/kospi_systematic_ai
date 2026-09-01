# v2 Phase 3 Technical Agent C 보고서

## 결론

`EXP-20260826-002`를 사전등록하고 Agent B Top 30 안에서만 14개 causal OHLCV
Feature를 평가했다. 선형·얕은 비선형 후보의 평균 Rank IC가 모두 음수여서 전 후보를
기각했다. 포트폴리오 백테스트와 손절·익절 최적화는 진행하지 않았다.

## 모델 결과

| 모델 | 평균 Rank IC | 평균 Brier | 평균 AUC |
|---|---:|---:|---:|
| hist dual | -0.0072 | 0.2501 | 0.5235 |
| linear dual | -0.0083 | 0.2489 | 0.5244 |

사전등록 선택 순서상 `hist_dual`이 진단상 덜 나빴지만, 음의 Rank IC이므로 승격
후보가 아니다. hist dual의 연도별 양수 IC는 2/5였다.

## no-trade 동작

예상 비용 차감 수익률이 양수이고 양수 확률이 55% 이상인 종목만 최대 10개로 제한했다.
1,233개 점수일 중 513일은 후보가 0개였고, 총 후보는 1,819행이었다. no-trade 자체는
작동했지만 남은 후보의 예측력이 유효하다는 뜻은 아니다.

## v1 교훈 반영

- 약한 점수로 보유 수를 강제하지 않고 0종목을 허용했다.
- 시장상태 veto나 EMA·순위 band를 추가해 성능 부족을 가리지 않았다.
- 결과가 음수인 상태에서 55% threshold와 Feature 관계를 재튜닝하지 않았다.
- 예측력이 확인되기 전에 포트폴리오 규칙·손절·익절을 최적화하지 않았다.

## 데이터·감사

- Agent B 입력: 44,310행, SHA-256 `e9e96532fcb9dbb5926cd9f3164d8ddcf5f5eeb240efcf7e043c159bd3caa23a`
- KRX 입력: 1,966개 파일, 2016-01-04~2023-12-28
- 학습·평가 표본: 8,782행
- 기계적 분할·병합 reset: 18건
- v2 2022~2023 consumed development: 실제 로드
- v1 Development Test 별도 파티션·Final OOS: 접근하지 않음
- 독립 재실행 6개 산출물: byte-identical
- Phase 3 전용 테스트: 4/4 통과
- 전체 회귀 테스트: 192/192 통과

## 산출물

- `artifacts/v2_phase3_agent_c_release_v2/fold_metrics.csv`
- `artifacts/v2_phase3_agent_c_release_v2/model_summary.csv`
- `artifacts/v2_phase3_agent_c_release_v2/daily_agent_c_candidates.csv.gz`
- `artifacts/v2_phase3_agent_c_release_v2/daily_candidate_counts.csv`
- `artifacts/v2_phase3_agent_c_release_v2/selected_model.json`
- `artifacts/v2_phase3_agent_c_release_v2/data_audit.json`
- `artifacts/v2_phase3_agent_c_release_v2/manifest.json`

## Codex Handoff

현재 Agent C 후보를 포트폴리오 단계로 넘기지 않는다. 다음 연구를 하려면 같은
2018~2023에서 threshold만 바꾸지 말고, 왜 일봉 OHLCV의 조건부 예측력이 없는지에 대한
새 가설과 별도 Experiment가 필요하다. 분봉은 별도 수집·PIT 감사·봉 내부 선후관계
계약 없이는 사용할 수 없다.
