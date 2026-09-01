# v2 Phase 6D Agent D6 사전등록 명세

## 연구 질문

고정 가중합과 원점수 0.05·0.075 진입 임계값을 사용하지 않고, 과거 연도만으로 적합한 비용차감 10거래일 초과수익 메타 회귀 순위가 Agent C3 단독 순위보다 나은가를 진단한다.

## 고정 구조

- 입력 Agent: 유지된 Agent B2와 Agent C3만 사용한다. 기각된 B4·C5는 사용하지 않는다.
- 학습: 2019년부터 평가연도 직전까지의 소비된 개발자료로 HistGradientBoostingRegressor를 확장형 재적합한다.
- 경계: 각 평가연도 시작 전 10거래일 purge를 적용한다. 2020~2023을 연도별로 한 번씩 예측한다.
- 결합: B2의 일별 `report_top30`을 먼저 통과시킨 후 D6 예상 초과수익 순위 상위 3개만 C 단계 진입 후보로 삼는다.
- 대조군: 같은 5거래일 재조정·상위 3개·10% 동일비중 조건의 C3 단독 순위다.
- 체결: t 종가 신호, t+1 시가, 5% gap veto, -5% 손절, +10% 익절, 최대 10거래일, 같은 봉 충돌은 STOP_FIRST다.
- 포트폴리오: 최대 10종목, 종목당 10%, 최소 보유 종목 수는 없다.
- 모델·임계값 grid search와 0.05·0.075 원점수 임계값은 사용하지 않는다.

## 증거 한계

2004~2023은 이미 관찰된 소비 개발자료다. 이 실험은 구조 비교 진단일 뿐 독립 Validation/OOS 증거가 아니며, 통과하더라도 거래 후보로 승인하지 않는다. `data/sealed/final_oos_v24/`와 2024년 이후 자료는 접근하지 않는다.

## 채택 gate

직렬 D6에 대해 순초과수익 양수, 4개 연도 중 3개 이상 연간 초과수익 양수, Sharpe 양수, MDD -30% 초과, C3 대조군보다 높은 순초과수익, 회계조정 PASS를 모두 요구한다. 통과 시에도 forward shadow 입력 후보로만 보류한다.

## 실행과 산출물

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m kospi200_agent_d6.cli run --config configs/v2_agent_d6_walk_forward_meta_rank.json --output artifacts/v2_agent_d6_walk_forward_meta_rank
```

산출물은 `candidate_metrics.csv`, `daily_agent_d6_scores.csv.gz`, 연도별 모델, `walk_forward_audit.json`, `data_audit.json`, `decision.json`, `selected_run/`, `manifest.json`이다.

## Codex Handoff

코드·설정·입력 hash를 결과 확인 전에 registry에 고정하고, 전용 테스트와 전체 회귀 테스트 및 독립 재실행의 byte determinism을 확인한다. 결과를 본 뒤 모델·기간·순위 수·비용·체결 규칙을 변경하지 않는다.
