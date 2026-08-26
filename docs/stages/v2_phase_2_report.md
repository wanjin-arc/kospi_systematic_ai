# v2 Phase 2 Fundamental Agent B 보고서

## 결론

`EXP-20260826-001`을 사전등록하고 PIT KOSPI 200 펀더멘털 순위 모델을 실행했다.
사전등록 선택 규칙에 따라 `ridge_a10`이 선택됐으며, 이는 다음 단계에서 사용할 일별
펀더멘털 후보 생성기일 뿐 독립 OOS 또는 거래 승인 모델이 아니다.

## 기간 정정

OpenDART 전체 재무제표 API의 독립 입력은 2015 사업연도부터다. 2015 보고서에는
2014 비교금액이 포함될 수 있지만, 그 금액은 해당 2015 보고서의 실제 접수일 다음
KRX 세션 전에는 사용할 수 없다. 따라서 2014 펀더멘털 관측으로 소급하지 않았다.
로컬 Factor 패널의 첫 실제 사용 가능일은 2016-03-24다.

## 일별 선택 계약

1. 실제 날짜별 KOSPI 200 구성종목을 사용한다.
2. 당일 시가총액 상위 200개를 먼저 제한한다.
3. 최신 확정 재무제표 20 Factor와 252세션 희석도를 사용한다.
4. 20% 이상 상장주식수 변화가 가격 역조정으로 상쇄되면 분할·병합 reset으로 처리한다.
5. Agent B 점수 상위 최대 30개를 일별 후보로 출력한다.

최종 산출물은 1,477일, 44,310행이며 모든 날짜에 30개가 존재한다. 날짜·ticker 중복은
0건이고 출력의 최대 시가총액 순위는 160위다. 희석도 coverage는 96.98%이며 기계적
reset은 124건이다.

## 모델 결과

| 모델 | 평균 Rank IC | 평균 NDCG@30 |
|---|---:|---:|
| Ridge alpha=10 | 0.0360 | 0.5616 |
| shallow HistGradientBoosting | 0.0276 | 0.5485 |
| equal composite | -0.0119 | 0.5366 |

Ridge의 연도별 IC는 6개 중 4개가 양수였고 2019·2021은 음수였다. 따라서 경제적
안정성은 아직 확인되지 않았다. Phase 2에서는 주문·비용·포트폴리오 백테스트를 수행하지 않았다.

## 감사와 재현성

- Factor 패널: 264,341행, 2016-03-24~2023-12-28
- 최소 사업연도: 2015
- 2014 독립 공시 로드 또는 비교금액 소급: 없음
- KRX market 파일: 1,966개, 2016-01-04~2023-12-28
- v2 2022~2023 consumed development: 실제 로드함
- v1 Phase 5 Development Test 별도 파티션 접근: 없음
- Final OOS 접근: 없음
- 독립 재실행의 5개 산출물 SHA-256: 전부 동일
- Phase 2 전용 테스트: 7/7 통과
- 전체 회귀 테스트: 188/188 통과

첫 실행은 설정에 등록한 embargo 63을 학습 cutoff에 별도로 적용하지 않은 구현 누락을
감사 중 발견해 무효로 보존했다. 연구 후보·target·기간은 바꾸지 않고 purge 63과 embargo
63을 모두 적용한 source hash를 재동결한 뒤 최종 실행했다.

## 산출물

- `artifacts/v2_phase2_agent_b_release/fold_metrics.csv`
- `artifacts/v2_phase2_agent_b_release/model_summary.csv`
- `artifacts/v2_phase2_agent_b_release/daily_top30.csv.gz`
- `artifacts/v2_phase2_agent_b_release/selected_model.json`
- `artifacts/v2_phase2_agent_b_release/data_audit.json`
- `artifacts/v2_phase2_agent_b_release/manifest.json`

## Codex Handoff

다음 단계는 Agent C 명세 확정이다. Agent C는 매일 Agent B Top 30 안에서만 OHLCV
기술 점수와 진입·청산을 판단해야 한다. `ridge_a10`을 결과를 보고 재조정하지 않으며,
Agent C target·모델·체결·비용·손절/익절 순서 규칙을 새 Experiment ID로 사전등록하기
전에는 포트폴리오 백테스트를 실행하지 않는다.
