# v2 Phase 6E 시계열 Agent B·C·D 실행 보고서

## 실행 범위

`EXP-20260827-001`~`003`을 결과 확인 전에 registry에 등록하고 실행했다. 모든 결과는 2004~2023의 이미 소비된 개발자료에 대한 구조 진단이다. 2024년 이후 자료 및 `data/sealed/final_oos_v24/`는 열람·스캔·로드·집계하지 않았다.

## Agent B5: 재무 시계열 XGBRanker

- 입력은 PIT 재무 패널, 공식 KOSPI 200 지수, 시가총액·희석 감사 필드뿐이다. OHLCV를 feature로 읽지 않았다.
- 21개 재무 factor의 단면 percentile, 존재가 검증된 robust z-score, 종목별 63·252세션 변화량으로 총 83개 feature를 만들었다.
- `XGBRanker(rank:ndcg)`의 2019~2023 expanding fold 평균 Rank IC는 **0.0411702**, 양(+) IC 연도는 **3/5**, 평균 NDCG@30은 **0.5608520**이었다.
- 기존 B2의 평균 Rank IC **0.0328378**보다는 높았지만, 기존 NDCG@80 **0.65654**보다 낮고 초반 2019~2020의 IC가 음수였다. 따라서 B2를 교체하거나 거래 후보로 승격하지 않는다.

## Agent C6: OHLCV LSTM·CNN 재적합

- 재무·업종·Agent B 입력 없이 40세션 OHLCV만 사용했다.
- LSTM 변동성 예측과 CNN의 `+10% 익절이 -5% 손절보다 먼저 발생할 확률` 예측을 고정된 C3 구조·seed로 재적합했다.
- 평균 초과수익 Rank IC **0.0477620**, 저점 확률 AUC **0.6640958**, 변동성 MAE **0.1175667**, 양(+) IC 연도 **5/5**로 기존 C3와 바이트 단위까지 동일하게 재현됐다.
- 이는 구조·입력 해시의 독립 동결이며 새 독립 검증 증거 또는 거래 승인이 아니다.

## Agent D7: B5 Top30 → C6 직렬 정책

- B5의 일별 Top30을 하드 게이트로 적용했다. 그 안에서 B 순위 percentile과 C6 점수 percentile을 0/0.5/1.0 가중치 grid로 결합했다.
- CNN 확률 0.55 이상은 5%, 0.65 이상은 11% 목표 비중으로 사전등록했다. 이는 과거 C 원점수 0.05/0.075를 임의로 재사용한 것이 아니다.
- 정책 선택 구간(2019~2020) 결과:

| 정책 | 순초과수익률 | 평균 현금 |
| --- | ---: | ---: |
| B 50% / C 50% | -45.10%p | 97.19% |
| B 0% / C 100% | -46.42%p | 97.19% |
| B 100% / C 0% | -51.95%p | 94.80% |

- 가장 덜 나쁜 B50/C50 정책을 기계적으로 선택해 2021~2023 소비 개발자료에서 진단한 결과는 전략 +0.091%, 지수 -10.476%, 순초과 +10.567%p였다. 그러나 평균 현금이 **99.30%**, 3년 절대수익이 사실상 0이고 선택 구간의 모든 정책이 실패했다. 지수 하락 방어를 종목선정 알파로 해석할 수 없다.
- 따라서 D7은 거래·모의투자·forward shadow 후보로 **승격하지 않는다**. 산출물의 `RETAIN_D7_FOR_FORWARD_SHADOW_ONLY` 문자열은 진단 구간의 제한된 코드 gate만 반영한 기계적 상태이며, 선택 구간 실패와 독립 OOS 부재를 덮어쓰는 승인 판정이 아니다.

## 재현성과 감사

- B5 primary/reproduction: 5개 파일 SHA-256 동일.
- C6 primary/reproduction: 6개 파일 SHA-256 동일.
- D7 primary/reproduction: 실행 원장을 포함한 18개 파일 SHA-256 동일.
- 전체 회귀: `PYTHONPATH=src python -m unittest discover -s tests -v` → **274/274 PASS**.
- B5/D7 전용 테스트: 시계열 lag, 선택 가능한 robust-z 열, Top30 하드 게이트, 확률 기반 비중, 구 원점수 임계값 금지를 검증했다.

## 산출물

- `artifacts/v2_agent_b5_temporal_xgbranker/`
- `artifacts/v2_agent_c6_lstm_cnn_refit/`
- `artifacts/v2_agent_d7_serial_b5_c6/`
- 각 경로의 `_reproduction/`은 동일 입력 재실행 결과다.

## 결론과 미결정 사항

이번 실행은 Agent B의 시간축 재무 표현과 Agent C의 LSTM·CNN 분리를 구현·검증했지만, 결합 Agent D의 선택 구간 성과가 실패했다. B5의 IC 개선만으로는 매매 의사결정의 경제적 효용을 보장하지 않으며, C6은 기존 C3를 재현한 것뿐이다. 소비된 개발자료에 맞춘 추가 임계값·가중치 조정은 수행하지 않는다. 새로운 구조를 다시 연구하려면 별도 Experiment ID, 선택 규칙, 아직 소비되지 않은 독립 검증 계획에 대한 사용자 승인이 필요하다.

## Codex Handoff

- 구현 파일: `src/kospi200_agent_b5/runner.py`, `src/kospi200_agent_d7/runner.py` 및 각 CLI·테스트.
- 다음 단계에서는 이 결과를 근거로 과거 개발기간에 다시 튜닝하거나 protected OOS를 열지 않는다.
