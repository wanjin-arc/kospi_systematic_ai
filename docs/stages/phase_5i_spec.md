# Phase 5I 2004 확장·점수 지속성·저회전 구조 명세

## 연구 질문

2004년부터 확장된 학습표본으로 고정 ElasticNet 종목점수를 적합하고, 매일 점수화는 유지하되 3세션 진입/이탈 지속성과 5세션 교체 주기를 적용하면 2011~2018 내부 walk-forward에서 거래비용 차감 KOSPI 100 초과수익을 만들 수 있는가.

## 사전등록

- Experiment ID: `EXP-20260825-004`
- 증거 지위: 이미 일부 결과를 본 기간을 포함하는 adaptive diagnostic
- 학습 시작: 2004-01-02
- 연도별 검증: 2011~2018, anchored 8개 fold
- Feature: Phase 4B의 종목 21개·시장 5개·상호작용 6개
- 모델: `elastic_a005_l02` 하나
- target: t 종가 신호, t+1 시가 진입, t+11 시가 청산의 10세션 KOSPI 100 초과수익 횡단면 순위
- purge/embargo: 각각 20세션

## 변경된 매매 구조

모든 적격 종목을 매일 점수화하고 causal EMA5 뒤 일별 순위화한다. 신규 진입은 3세션 연속 상위 10위이며 5세션 교체일인 종목만 허용한다. 일반 이탈은 3세션 연속 20위 밖이며 교체일인 경우다. 최대 보유 20세션, 최대 10종목, 종목당 10%, 최소 보유 0, no pyramiding이며 현금은 자유롭게 남긴다.

## gate와 해석

연결 기본비용 순초과수익률이 양수이고 2배 비용에서도 비음수일 때만 구조 진단을 통과한다. 연도별 양수 비율은 regime 진단이며 hard gate가 아니다. 이미 소비된 기간이므로 통과해도 거래·Development Test 후보로 자동 승격하지 않고, 기존 D20도 변경하지 않는다.

## 금지

2019년 이후 자료, Development Test, Final OOS, DART/재무/뉴스 Factor, 분봉, 결과 확인 후 재조정, 레버리지·공매도는 사용하지 않는다.

## 산출물과 완료 조건

`artifacts/phase5i_2004_hysteresis_rebalance/`에 metrics, fold audit, score/policy/data audit, run, manifest를 저장한다. 독립 재실행의 byte determinism과 전체 회귀 테스트를 통과해야 한다.

## Codex Handoff

설정은 `configs/phase5i_2004_hysteresis_rebalance.json`, 실행은 설정의 `run_command`를 따른다. 실행 전에 registry의 code/config/data/policy hash를 동결한다.
