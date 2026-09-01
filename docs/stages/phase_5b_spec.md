# Phase 5B 다변수 일별 횡단면 Ranking 명세

## 1. 연구 질문

21개 종목 기술변수의 일별 횡단면 순위, 5개 동시점 시장상태 및 6개 고정 상호작용을 사용한 제한된 선형·비선형 모델이 2015~2018 내부 Validation에서 거래비용 차감 후 KOSPI 100 가격지수를 안정적으로 상회하는가.

## 2. 거시적 시스템 구조

```text
t일 종가까지의 종목·시장 내부 변수
→ 종목별 Feature percentile rank
→ Train-only 전처리와 모델 점수
→ 같은 날 KOSPI 100 적격 종목 점수 순위
→ 상위 10개를 t+1 시가 주문 후보로 제출
→ 10세션 보유, no pyramiding, 비용·세금·slippage 반영
```

모든 적격 종목은 매 거래일 같은 계산 체계로 점수화한다. 출력 점수는 다시 날짜별 percentile rank로 정규화하고 `score 내림차순, security_id 오름차순`으로 동률을 해소한다.

## 3. 후보와 Train-only 적합

- Equal-weight Feature rank
- Ridge alpha 1, 100
- ElasticNet alpha 0.005, l1 ratio 0.2
- HistGradientBoosting depth 2, 3
- 사전 고정한 Ridge/HistGradientBoosting 50:50 rank blend

결측 대체, 시장상태 표준화, 선형계수, tree split은 각 fold의 Train에서만 적합한다. Random split, 결과 확인 후 후보 추가, 임계값 변경, Feature 삭제는 금지한다.

## 4. 포트폴리오와 gate

- 초기자금 5,000,000원
- 최대 10종목, 종목당 10%, long-only, no pyramiding
- target과 정렬한 10거래세션 보유
- t 신호 → t+1 시가 주문, 5% entry gap cap
- 기존 수수료·세금·10bp adverse slippage, 2배·3배 stress

거래 후보가 되려면 기본비용 기준 2015~2018 네 연도의 순초과수익률이 모두 0 이상이고 연결 순초과수익률이 0보다 커야 한다. 통과 후보끼리는 연결 순초과수익률, Sharpe, MDD, turnover, 복잡도 순으로 선택한다. 통과 후보가 없으면 가장 나은 후보를 진단용으로만 기록하고 전부 기각한다.

## 5. 데이터 경계와 비목표

- 입력 최대일 2018-12-31
- 2019~2021 재평가·재최적화 금지
- Development Test 실행 금지
- Final OOS 접근 금지
- 신규 외부·재무·뉴스 데이터 금지
- 실거래·배포 금지

## 6. 산출물과 완료 조건

- `artifacts/phase5b/selection/candidate_portfolio_metrics.csv`
- `artifacts/phase5b/selection/fold_rank_metrics.csv`
- `artifacts/phase5b/selection/fold_audit.csv`
- `artifacts/phase5b/selection/feature_relationships.csv`
- `artifacts/phase5b/selection/candidate_selection.json`
- `artifacts/phase5b/selection/selected_model.json`
- `artifacts/phase5b/selection/score_contract.json`
- `artifacts/phase5b/selection/data_audit.json`
- `artifacts/phase5b/selection/run.json`
- `artifacts/phase5b/selection/manifest.json`

완료 조건은 설정·코드·데이터·후보군 hash 동결, 관련 및 전체 테스트 통과, byte determinism, gate 결과의 fail-closed 기록이다. 이 단계만으로 Development Test나 거래 모델 승인을 의미하지 않는다.

## Codex Handoff

- 설정: `configs/phase5b_multifactor_ranking.json`
- 구현: `src/kospi100_multifactor/`
- 실행: `PYTHONPATH=src python -m kospi100_multifactor.cli select --config configs/phase5b_multifactor_ranking.json --output artifacts/phase5b/selection`
- Development Test 명령은 구현하지 않거나 항상 거부한다.
