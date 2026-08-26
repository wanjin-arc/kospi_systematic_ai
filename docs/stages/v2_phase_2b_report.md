# v2 Phase 2B Agent B 품질·하방위험 실행 보고서

## 결론

`EXP-20260826-005`에서 `ridge_quality`가 선택됐다. 평균 품질 Rank IC는 `0.03284`, NDCG@80은 `0.65654`였지만 연도별 IC는 3/5만 양수였다. 2019·2021 IC가 음수이고 Top80 실제 초과수익도 2019·2023에 음수였으므로 안정적인 펀더멘털 모델로 승격하지 않는다.

기존 Agent B보다 공식 KOSPI 200 초과수익과 하방위험이라는 역할은 명확해졌으나 Agent D2의 진단 입력 후보일 뿐이다.

## 결과

| 모델 | 평균 품질 Rank IC | NDCG@80 | 양의 IC 연도 |
|---|---:|---:|---:|
| Ridge quality | 0.03284 | 0.65654 | 3/5 |
| Hist quality | 0.01982 | 0.65207 | 3/5 |

Ridge 연도별 IC는 2019 `-0.00795`, 2020 `0.04196`, 2021 `-0.05059`, 2022 `0.10210`, 2023 `0.07867`이다.

## 데이터·감사

- 재무 Factor 입력: 264,341행, 2016-03-24~2023-12-28
- 공식 KOSPI 200 지수: 코드 1028, 4,945행
- 월말 label: 12,323행
- 일별 지연 적용 점수: 177,882행
- 월말 점수는 같은 날 사용하지 않고 다음 거래일부터만 확장
- 본 실행과 독립 재실행 6개 파일 byte-identical
- 포트폴리오 백테스트: 없음
- v1 Development Test·Final OOS 접근: 없음

## 산출물

- `artifacts/v2_phase2b_agent_b_quality_release/`
- `artifacts/v2_phase2b_agent_b_quality_release_reproduction/`

## Codex Handoff

`ridge_quality` 전체 점수와 Top80 flag는 Agent D2에서 필터·위험 calibration 후보로만 사용할 수 있다. Top30 hard gate 또는 단순 순위 가중치로 되돌리지 않는다.
