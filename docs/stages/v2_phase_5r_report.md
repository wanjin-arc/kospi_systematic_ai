# v2 Phase 5R — 동결 모델 Predict-only 무결성 차단 보고서

## 1. 결론

`EXP-20260901-002`는 포트폴리오 성과를 계산하거나 경제 gate를 판정하지 않고 데이터
무결성 단계에서 기각한다.

최종 결정은 `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`다. 동결 C_ONLY 모델의
적합 여부가 아니라, 평가기간의 corporate action 회계조건과 역사적 stable identity가
불완전해 자기금융 포트폴리오와 EX2 수익률을 정당하게 만들 수 없기 때문이다.

DEC-105 후속 감사에서 원천 Phase 4E 모델의 라벨 무결성 오류도 확인됐으므로 이 Phase 5R
점수·주문 의도 자체를 후속 입력으로 사용하지 않는다. corporate-action·identity 차단 결론은
유효하지만, 실행 이력은 `SUPERSEDED_PHASE5R_INVALID_PHASE4E_SOURCE`로 보존하고 새 Phase 4
모델이 검증된 뒤 별도 Experiment ID에서 predict-only 감사를 다시 수행한다. 이것은 Phase 5
통과가 아니며 70/20/10 구조의 성과 증거도 아니다.

## 2. 두 실행 시도와 관측 경계

첫 시도는 `2021-04-15` 카카오 `035720`의 관측 share reset을 처리하는 과정에서 중단됐다.
당시 관측 action은 ratio와 cash-in-lieu price를 가졌지만 `source_status`가 engine의
`READY` 계약과 달랐다. artifact·공개 metric·경제 gate는 생성되지 않았다.

DEC-103은 이를 Phase 5R 전용 builder에서 open/직전 close와 상장주식 수 역비율이 맞으면
`READY`로 넘기는 호환성 문제로 판단했다. 두 번째 시도는 이 계약으로 카카오를 지난 뒤
`2021-01-15` 아시아나항공 `020560`의 모호한 share reset을 포함한 EX2 계산에서 중단됐다.
두 번째 시도도 결과 파일·포트폴리오 성과·경제 gate를 남기지 않았다.

성과가 관측되기 전에 `docs/V25_KOSPI_RAW_AUDIT_KO.md`와 대조해 DEC-103의 전제가
권위 데이터 계약과 충돌함을 확인했다. 따라서 두 시도의 중간 계산은 연구 결과로 사용하지
않고, DEC-104가 DEC-103을 append-only로 supersede한다.

## 3. 오류와 원인

관측 `listed_shares` 변화와 `effective-day open / prior close`의 역관계는 corporate action
후보를 찾는 진단에는 유용하지만, 다음 네 증거를 대신하지 못한다.

1. PIT 안정 종목 identity와 당시 지수 편입
2. 원문 공시 또는 구조화 응답의 권리·분할 비율
3. 효력일과 실제 거래세션
4. KRX 가격·상장주식수의 동일 배율 교차검증

현재 미해결 corporate action 자료에는 이 네 조건을 모두 만족하는 승인 terms가 없다.
또한 `KRX_COMMON:<ticker>` 형식은 ticker를 재포장한 값으로, 코드 변경·우선주 표기·합병을
가로지르는 역사적 stable security identity를 증명하지 않는다. 영문이 섞인 원천 ticker를
숫자만 남겨 정규화하면 서로 다른 증권이 같은 6자리 코드로 충돌할 수도 있다.

2021~2023 원천을 정확한 6자리 숫자 ticker만으로 별도 감사한 결과, 연속 세션의
`listed_shares` 20% 이상 변화는 223건이었다. 그중 전일·당일 모두 KOSPI 200 구성종목인
사건은 37건이고 모두 membership이 이어졌다. open 기준 15% 역비례 진단을 통과한 사건도
전체 42건에 불과했으며, 통과 여부와 관계없이 네 증거를 모두 갖춘 승인 terms는 0건이다.
삼성전자·SK하이닉스 해당 사건은 0건이므로 두 종목 제외만으로 이 문제가 사라지지 않는다.

추가로 기존 숫자추출 정규화는 원천 `00680K`와 `000680`을 모두 `000680`으로 만들 수 있는
identity collision을 가진다. 따라서 Phase 5R preflight는 원천 ticker가 정확히 `^\d{6}$`인지
검사하고 그 외 코드는 임의 변환하지 않은 채 unresolved identity로 차단해야 한다.

old-holder의 정확한 수익률을 만들려면 수량 배율뿐 아니라 cash distribution, successor
security 가치, 청약 납입액과 권리 조건이 필요하다. 이를 모르는 상태에서 reset 종목을
사후 제외·재가중하거나 보유수량을 역비율로 바꾸는 것은 자기금융 회계가 아니다.

## 4. 허용한 감사와 금지한 계산

허용 범위는 다음으로 제한한다.

- Phase 4E bundle·manifest·Feature·runtime 무결성 확인
- 동결 C_ONLY의 predict-only 점수 생성과 `fit` 호출 0건 확인
- 2021~2023 share-reset 후보 ledger와 identity 공백 감사
- 실행 전에 고정된 70/20/10 포트폴리오의 주문 **의도** 구성 감사
- 공식 KRX1028 원시 지수 확인
- EX2의 두 비자기금융 민감도 진단

미해결 후보 또는 identity 공백이 하나라도 평가 경로에 있으면 backtest engine,
보유수량·원가 조정, 거래원장, strategy/neutral 수익률과 경제 gate를 계산하지 않는다.

실제 최종 감사 실행은 동결 C_ONLY 점수 143,323행과 36회 리밸런싱의 차단된 주문 의도
3,600건을 만들었다. 원천 정확한 6자리 ticker 기준 share-reset 후보는 223건, 로더가 반환한
과거 구성종목 집합 안의 후보는 86건, 전일·당일 모두 실제 구성종목인 사건은 37건이었다.
원천 비정규 ticker 행은 15,490건이고 숫자추출 규칙이 서로 다른 원천 코드를 같은 값으로
합치는 collision은 4개였다. 그 예에 `00680K`와 `000680`이 포함된다. 이 수치는 후보·identity
감사값이며 기업행위의 종류나 경제조건을 확정하지 않는다. 2021~2023 실제 membership ticker와
교차한 normalization collision은 0개였다. 별도 2004~2020 후속 감사에서도 membership 원천의
비정규 ticker는 0행, 시장 원천의 전역 collision은 4개, Phase 4E membership 교차 collision은
0개였으므로 이 특정 충돌이 동결 모델에 유입됐다는 증거는 없다.

## 5. EX2 해석 제한

- `EX2_PRICE_UNIT_SENSITIVITY`: old-holder 권리 조정 없이 관측 가격 단위를 잇는 민감도
- `EX2_ISSUER_CAP_VALUE_SENSITIVITY`: 관측 시가총액 변화를 잇는 민감도

두 계열 모두 직전 구성종목을 reset 당일 사후 제거하거나 survivor-only로 재가중하지 않는다.
그러나 둘 다 배당·현금납입·교환·승계 증권을 완전히 회계 처리하지 못하므로 비자기금융이다.
따라서 canonical EX2 return, 수익률 상·하한, 거래 가능한 benchmark 또는 경제 gate의
대체물로 표현하지 않는다.

- `stable_identity_contract_complete=false`
- `canonical_ex2_return_evaluable=false`
- EX2 경제 gate: `NOT_EVALUATED`

## 6. 성과·gate 판정

다음 항목은 모두 `NOT_EVALUATED`다.

- Phase5R 총수익률·Sharpe·MDD·turnover·평균 노출
- `Phase5R - NEUTRAL_CORE` 모델 alpha
- 공식 KRX1028 대비 연도별·rolling 12개월 열위와 downside capture
- canonical EX2 대비 초과수익·하방 방어
- 기본비용·2배 비용 stress
- 30건 청산 gate

`NOT_EVALUATED`는 0% 수익, gate 실패 수치 또는 현금 100% 전략을 뜻하지 않는다. 유효한
회계 성과 자체를 만들지 않았다는 뜻이다. 두 EX2 민감도가 우연히 같은 방향을 보이더라도
경제 gate를 통과한 것으로 세지 않는다.

## 7. 최종 판정과 보존 범위

- decision: `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`
- canonical portfolio performance: `NOT_EVALUATED`
- canonical EX2 performance: `NOT_EVALUATED`
- 모델 fit·calibration·B/C/D 재선택: 0건
- Phase 4E 모델 변경: 없음
- protected OOS 접근: 없음
- 실제 주문·외부 실행: 없음
- portfolio engine 호출·성과 metric 생성: 0건
- 실행 가능한 corporate action 생성: 0건
- primary/reproduction 감사파일: `10/10` byte-identical
- Phase 4E·5R 전용 회귀: `68/68` PASS
- 물리 격리 shadow 전체 회귀: `342/342` PASS
- Phase 5R code hash: `f2b7c5ea54a48fdc6d1b423bc341148a916369fe07e6d52944c064c612344216`
- config hash: `c2a5a3720c139a96cc491667ebce4711cdd14fe0dc705b609c0149802fb08f2b`
- data version: `cf5f7ad088b74aa2a98160c3dbe3fe4e59ef1af2798d975b707d1f242ca5c288`
- manifest SHA-256: `020805e5ff154641a123b5ae9bc3346b25252385365180f06f4e8703dc6e18e3`

사전등록 70% 동일비중 유동성 core + 20% C_ONLY alpha tilt + 10% 현금 구조는 성과로
검증되지 않았다. 그러므로 이 구조가 안정적이라고 채택하거나 실패했다고 경제적으로
단정하지 않는다. 현재 기각 사유는 데이터 회계 무결성이다.

## 8. 재개 조건

1. 원천 ticker를 변형 없이 보존하고 당시 issuer·share class·successor를 연결한 stable
   security identity map을 만든다.
2. 네 증거 요건을 모두 통과한 corporate-action terms ledger를 만든다.
3. split·reverse split뿐 아니라 유상증자·감자·합병·회사분할·주식교환의 holder multiplier,
   cash distribution, successor value와 subscription outflow를 명시한다.
4. 승인 terms가 없는 구성종목·보유 경로는 fail-closed하는 단위 테스트를 추가한다.
5. 새 데이터 버전·코드·config hash와 새 Experiment ID를 결과 확인 전에 등록한다.
6. superseded Phase 4E bundle은 사용하지 않는다. DEC-105로 재학습한 새 모델을 결과 확인 전
   동결하고, 제외 두 종목·70/20/10 비중·비용·gate는 2021~2023 결과를 보고 재조정하지 않는다.

2004~2023은 계속 소비 개발자료다. 위 계약을 복구해도 독립 OOS나 최종 Phase 5 통과로
바뀌지 않으며, 최종 증거는 동결 후 새 forward 자료에서만 쌓는다.

## 9. 허용 산출물과 재현 범위

- 본 실행: `artifacts/v2_phase5r_integrity_soft_fusion/`
- 독립 재현: `artifacts/v2_phase5r_integrity_soft_fusion_reproduction/`
- 허용 파일: 동결 model score, share-reset candidate ledger, 공식 KRX1028 원시 비교자료,
  차단된 주문 의도, EX2 share-reset event ledger, 두 EX2 sensitivity, `audit.json`,
  `decision.json`, `manifest.json`
- 금지 파일: strategy/neutral 수익률, 기본·2배 비용 성과, exposure-matched 수익률,
  체결·포지션 원장

primary와 reproduction의 10개 파일은 모두 byte-identical했다. 민감도 CSV가 존재하더라도
성과 산출물로 세지 않는다.

## Codex Handoff

- 구현 대상: stable identity map loader, 승인 corporate-action terms schema·validator,
  self-financing position/benchmark accounting과 unresolved-event preflight.
- 관련 파일: `src/kospi200_phase5r/`, 새 versioned processed identity/terms release,
  `tests/test_kospi200_phase5r_*.py`, 새 Experiment 설정·registry 행.
- 필수 불변조건: 관측 price/share 역관계만으로 `READY` 생성 0건, unresolved event가 있으면
  engine 호출 0건, 사후 종목 제거·재가중 0건, 두 EX2 민감도를 canonical return으로 승격 0건.
- 완료 조건: 네 증거 요건, stable identity, 자기금융 reconciliation, 전용·전체 회귀와
  primary/reproduction byte determinism을 모두 통과한 뒤에만 성과 평가를 시작한다.
- 금지 작업: DEC-103 재사용, 같은 기간 성과를 보기 위한 우회 proxy, superseded Phase 4E
  bundle 재사용, protected OOS 접근, 실제 주문·배포. DEC-105 새 Experiment의 보수적
  Phase 4 재학습은 허용한다.
