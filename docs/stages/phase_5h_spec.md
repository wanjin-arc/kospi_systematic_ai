# Phase 5H KOSPI 전체 시장상태 상호작용 순위모델 명세

## 연구 질문

기존 Phase 5B와 동일한 모델·포트폴리오 조건에서 KOSPI 전체의 동시점 시장상태와 KOSPI 100 기술순위의 상호작용을 전부 추가하면 2015~2018 내부 순위 예측 및 비용 차감 성과가 개선되는가를 검증한다.

Phase 4C 결과를 보고 상위 상호작용만 고르지 않는다. 21개 종목 기술순위, 4개 시장상태, 84개 모든 조합을 고정 입력으로 사용한다. 이 구조는 Phase 5B의 단일 종목신호 불안정, 고회전율 및 복잡한 tree의 실패를 고려하여 규제 선형모델을 동일 후보군 안에서 비교할 수 있게 한다.

## 입력·기간·금지사항

- 입력은 2018년 이하 물리 KOSPI 100 partition과 Phase 4C 참조 partition뿐이다.
- anchored internal Validation은 2015, 2016, 2017, 2018이다.
- target은 t+1 시가~t+11 시가 10세션 KOSPI 100 초과수익률 횡단면 rank다.
- purge와 embargo는 각각 20세션이다.
- 2019~2021 재사용, Development Test, Final OOS, Feature 결과 기반 선택은 금지한다.

## 모델·포트폴리오·gate

후보 7개와 순서는 Phase 5B와 같다: equal-weight rank, Ridge 1·100, ElasticNet, shallow HistGradientBoosting 2개, Ridge/tree blend. 매일 모든 적격 KOSPI 100 종목에 점수와 순위를 매기며 t+1 이후 주문만 가능하다. 최대 10종목, 종목당 10%, 10세션 보유, no pyramiding, 비용·슬리피지는 Phase 5B와 동일하다.

채택하려면 연결 기본비용 순초과수익률이 양수이고 네 연도 모두 순초과수익률이 0 이상이어야 한다. 실패하면 모든 후보를 기각하고 진단상 최선만 보존한다. Development Test는 실행하지 않는다.

## Codex Handoff

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\run_phase5h_market_interaction_ranking.py --config .\configs\phase5h_market_interaction_ranking.json --output .\artifacts\phase5h_market_interaction_ranking
```
