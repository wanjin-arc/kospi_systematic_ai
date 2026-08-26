# v2 Phase 4 Agent D 실행 보고서

## 결론

`EXP-20260826-004`는 사전등록한 네 후보를 모두 실행했으며 Agent D를 기각했다. 진단상 최선은 펀더멘털 Agent B를 전혀 섞지 않은 `C100`이었다. 따라서 현재 Agent B 점수를 단순 가중 결합하는 방식은 Agent C 단독보다 성과를 개선하지 못했다.

이 결과는 2019~2023의 이미 소비된 개발기간 진단이다. 거래 승격이나 독립 OOS 성과의 근거가 아니며, v1 Development Test 물리 파티션과 Final OOS에는 접근하지 않았다.

## 고정한 구조

- Agent C 점수 `0.05` 이상은 목표비중 5%, `0.075` 이상은 11%
- 신호는 t일 종가 뒤 확정하고 t+1 시가에서만 주문
- t+1 시가 gap 절댓값이 5%를 넘으면 신규 매수 거부
- 손절 -5%, 익절 +10%, 최대 10세션, 같은 일 손절·익절 충돌 시 손절 우선
- 최대 10종목, 최소 보유 0종목, pyramiding 금지
- Agent B는 종목을 제거하지 않고 일별 순위 가산점으로만 결합
- 후보: `C100`, `B25_C75`, `B50_C50`, `B75_C25`
- commission 2bp/side, slippage 10bp/side, 역사적 매도세율 적용
- benchmark는 공식 지수가 아닌 `PIT_KOSPI200_CAP_WEIGHTED_PROXY`

## 후보별 결과

| 후보 | 총수익률 | Proxy 수익률 | 순초과수익률 | Sharpe | MDD | 양의 연도 |
|---|---:|---:|---:|---:|---:|---:|
| C100 | 8.49% | 30.57% | -22.07%p | 0.183 | -31.98% | 1/5 |
| B25_C75 | -4.38% | 30.57% | -34.95%p | 0.011 | -31.14% | 2/5 |
| B50_C50 | -19.11% | 30.57% | -49.68%p | -0.231 | -39.58% | 1/5 |
| B75_C25 | -17.64% | 30.57% | -48.21%p | -0.208 | -37.14% | 1/5 |

선택 규칙상 `C100`이 가장 나았지만 총 순초과수익률, 양의 연도 3/5, MDD -30% 초과 조건을 실패했다. reconciliation은 모든 후보가 통과했다.

## 원인 판단

1. Agent C의 횡단면 예측력은 양수였지만 높은 회전율(평균자산 대비 244.30배)과 실제 비용을 이길 만큼 강하지 않았다.
2. Agent B를 25%만 섞어도 순초과수익률이 -22.07%p에서 -34.95%p로 악화했다.
3. Agent B와 C의 일별 점수 상관이 약한 음수라는 사실이 분산효과로 이어지지 않았고, 현재 63세션 횡단면 재무 순위 target이 10세션 기술 매매의 진입 품질과 정렬되지 않았다.
4. 따라서 같은 기간에서 Agent D 가중치만 더 촘촘하게 조정하지 않는다. 다음 실험은 Agent B의 target·업데이트 주기·점수 보정 구조를 별도 Experiment로 다시 사전등록해야 한다.

## 감사와 재현성

- Agent B 입력: 44,310행
- Agent C 입력: 243,829행
- PIT membership: 246,780행
- 시장 입력: 1,233개 일별 파일
- 기계적 주식수 reset: 15건
- v1 Development Test 물리 파티션 접근: false
- Final OOS 접근: false
- 독립 재실행: 16개 파일 전부 byte-identical
- `decision.json` SHA-256: `8197f8614da69b866b6e6e77aef3222928a353d7345a4285e655e90a169bcc1f`

## 산출물

- 본 실행: `artifacts/v2_phase4_agent_d_release/`
- 독립 재실행: `artifacts/v2_phase4_agent_d_release_reproduction/`
- 후보 비교: `candidate_metrics.csv`
- 접근 감사: `data_audit.json`
- 결정: `decision.json`
- 실행 manifest: `manifest.json`

## Codex Handoff

Agent D의 단순 B/C 가중 결합은 종료한다. 후속 연구를 승인한다면 Agent B를 10세션 진입과 억지로 맞추기보다, 펀더멘털의 느린 시간축을 유지하면서 보유 가능성·장기 품질·하방위험을 예측하는 별도 target과 calibration을 먼저 설계한다. 동일 2019~2023에서 B 가중치만 재탐색하지 않으며, 새 구조는 새 Experiment ID와 향후 forward shadow 평가 계약을 가져야 한다.
