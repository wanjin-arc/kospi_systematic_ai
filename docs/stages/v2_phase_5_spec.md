# v2 Phase 5 — Agent D5 관계 확률 결합 사전등록 명세

Experiment ID는 `EXP-20260826-012`다. 2021~2023은 과거 실험에서 이미 결과를
관찰한 소비된 개발기간이므로 독립 Test/OOS가 아니다. 모델 선택은 2020년 이하에서
끝내고 2021~2023은 한 번의 최종 개발 진단과 연도별 regime 점검에만 사용한다.

## 연구 질문

Agent B2의 장기 품질 percentile과 Agent C3의 LSTM·CNN 성공확률ㆍ기술 순위ㆍ예상
변동성 사이의 비선형 관계가 2대1 거래 성공확률을 개선하는가. 관계 모델 확률과
B/C 점수 가중합을 결합한 진입 점수가 실제 비용 이후 공식 KOSPI 200을 개선하는가.

## 입력과 기간

- Agent B2: `EXP-20260826-005`의 일별 품질 percentile
- Agent C3: `EXP-20260826-008`의 LSTM 변동성ㆍCNN 성공확률ㆍ기술점수
- 관계 모델 적합: 2019-01-02~2019-12-02
- 결합비ㆍ임계값 선택: 2020-01-20~2020-12-30
- 최종 관계 모델 적합: 2019-01-02~2020-12-01
- 소비된 개발 진단: 2021-01-18~2023-12-28
- purge 10세션, embargo 10세션
- Final OOS 및 v1 Development Test 접근 금지

2011~2014 DART 원문은 구조 분류만 완료됐고 수치계정ㆍ역사적 identity 감사가
완료되지 않았으므로 이번 모델 입력은 0행이다. 이를 포함했다고 주장하지 않는다.

## 모델과 변수 관계

얕은 `HistGradientBoostingClassifier` 하나만 사용한다. 입력은 B percentile, C percentile,
CNN 성공확률, LSTM 변동성 percentile과 다음 고정 관계항이다.

- B×C
- B×CNN 확률
- C×CNN 확률
- B/C 순위 일치도
- 변동성으로 감쇠한 C 순위

최종 점수는 관계모델 성공확률에 B/C 가중합을 곱해 계산한다. B 비중
`0/25/50/75%`, 성공확률 `50/55/60%`, 당일 점수 percentile `90/95%`의 24개 정책만
2020년에서 비교한다. 5세션마다 최대 10종목, 종목당 10%, t+1 시가, gap 5% veto,
손절 5%, 익절 10%, 최대 10세션을 고정한다.

## 완료와 해석

2021~2023 연결 순초과수익 양수, 3개 연도 중 2개 이상 양수, Sharpe 양수, MDD
`-30%` 초과, 원장 대사를 모두 요구한다. 통과해도 독립 OOS가 아니므로 거래 승인이
아니며, 동결 뒤 forward shadow 후보로만 보존한다. 실패하면 거래 모델로 기각하고
동일 기간에서 추가 모델ㆍ가중치ㆍ임계값을 만들지 않는다.

## Codex Handoff

`src/kospi200_agent_d5/`, 설정, 테스트와 구조화 산출물을 구현한다. registry와 source,
config, 입력 hash를 기록하고 전체 테스트 및 byte determinism을 확인한다. 명령은 다음과 같다.

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m kospi200_agent_d5.cli run `
  --config configs\v2_phase5_agent_d5_relationship_probability.json `
  --output artifacts\v2_phase5_agent_d5_relationship_probability_release
```
