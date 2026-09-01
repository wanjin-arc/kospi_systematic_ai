# v2 Phase 4E — 무결성 복구 AI 점수모델 실행 보고서

## 1. 결론

`EXP-20260901-001`은 모델 전용 단계로 실행됐지만, DEC-105 후속 라벨 감사로 동결 판정을
철회했다. 2020-12-30 이하의 물리 입력과 당시 유효하다고 판정한 라벨로 Agent B·C·D를 시간순
OOF 비교해 `C_ONLY` HistGradientBoosting을 선택했으나, 이후 2019~2020 선택 표본의 유효 라벨
10행이 미해결 20% 이상 주식수 변화 경계를 통과했음을 확인했다. 이 결과와 bundle은
`SUPERSEDED_PHASE4E_LABEL_INTEGRITY`이며 후속 모델 입력으로 사용하지 않는다.

포트폴리오·주문·체결·성과 선택은 수행하지 않았다. 아래 수치는 오류가 발견되기 전 실행을
삭제하지 않고 보존한 역사적 감사값이며 새 모델의 성능으로 인용할 수 없다. 독립 OOS 성과나
거래 적합성, 최종 Phase 5 통과를 뜻하지 않는다.

## 2. 입력·경계 감사

- 물리 release: `data/processed/v2_phase4e_ai_model_2004_2020_v2/`
- release ID: `V2-P4E-INTEGRITY-20260901-002`
- 시장·membership·지수 최대 로드일: `2020-12-30`
- 실제 fit 최대 신호일: `2020-11-27`
- 실제 fit label 최대 exit date: `2020-12-29`
- fit 행: 23,567
- score panel 행: 801,007
- Selection OOF score 행: 4,876
- label이 없어 metric에서 제외됐지만 현재 score Universe에 유지한 행: 239
- 삼성전자 `005930`·SK하이닉스 `000660`의 모델행·횡단면 순위·점수: 0
- 포트폴리오 접근·주문 생성: 0
- 2021년 이후 fit 행: 0
- protected OOS 접근: 없음

동결 뒤 원천 ticker 정규화 위험을 2004-01-02~2020-12-30 전체에서 추가로 읽기 전용
감사했다. membership 4,206개 파일·841,657행은 비정규 ticker가 0행이었다. 시장 원천
4,206개 파일·5,488,813행에는 비정규 ticker 17,916행과 전역 normalization collision
4개가 있었지만, Phase 4E의 실제 PIT membership ticker와 교차한 collision은 0개였다.
따라서 이 정규화 충돌이 동결 C_ONLY 학습 표본에 유입됐다는 증거는 없다. 다만 이 검사는
역사적 stable identity나 보유수량 회계를 확정하지 않으므로 Phase 5R의 차단 사유를 해소하지
않는다.

DEC-105 라벨 경계 후속 감사의 funnel은 전체 거래소 원천 exact ticker 후보 4,391건,
로더의 ever-member·삼성전자/하이닉스 제외 모집단 554건, 전일·당일 실제 구성종목 후보
247건이었다. 두 종목 제외 전 양일 구성 후보는 248건이며 차이 1건은 삼성전자 `005930`의
2018-05-04 50:1 액면분할이었다. 기존 최종 fit 유효 라벨 23,567행 중 75개 고유 사건을
가로지른 83행이 있었고, 83행 모두 기존 `mechanical_reset=false`였다. 연도별로는 2011년 9,
2012년 4,
2013년 8, 2014년 13, 2015년 11, 2016년 8, 2017년 6, 2018년 14, 2019년 3, 2020년
7행이다. Selection 유효 OOF에서는 10행이 누락 경계를 통과했다.

미해결 corporate action 후보 파일은 evidence·hash·count 감사에만 사용했다. filing date를
reset·진입 차단·강제청산 시점으로 사용한 행은 없다. inverse price/share reset과
membership·identity gap을 가로지르는 라벨은 무효화했지만, 경제조건은 추정하지 않았다.

## 3. 모델 선택 결과

| 후보 | 평균 Rank IC | 비음수 연도 | 평가 연도 | 평균 Top10 target quality |
|---|---:|---:|---:|---:|
| `B_ONLY` | -0.003065 | 0 | 2 | -0.062684 |
| `C_ONLY` | 0.027545 | 2 | 2 | -0.057617 |
| `D_SOFT_FUSION` | 0.026551 | 2 | 2 | -0.055455 |

`C_ONLY`의 연도별 Rank IC는 2019년 0.014653, 2020년 0.040437로 모두 비음수였다.
`D_SOFT_FUSION`은 C 단독보다 평균 Rank IC를 엄격히 개선하지 못했으므로 선택하지 않았다.
선택 규칙은 포트폴리오 수익률을 사용하지 않았다.

후속 읽기 전용 label-only 민감도에서 누락 83행만 무효화하고 같은 OOF 절차를 메모리에서
재학습하면 B 평균 IC 0.003487(비음수 2/2), C 0.019761(1/2), D 0.019473(1/2)로 C 순서는
유지됐지만 연도 안정성은 2/2에서 1/2로 약화됐다. C 연도 IC는 2019년 -0.029770,
2020년 0.069292였고 독립 메모리 실행 2회의 metric은 같았다. fit은 23,484행, D fit은 9,220행이었고
model-state hash도 `725ddd903ea91e5633c476d6f2dedd95a0fda12ab40b1bd97b029f06e0424c64`로
바뀌었다. 이 민감도는 기술 Feature segment reset을 적용하지 않아 artifact·승격 후보가 아니며,
새 Experiment 전체 재학습 필요성을 확인하는 감사값으로만 사용한다.

Agent B의 첫 실행은 2017 fold에서 YoY growth Feature 5개가 전부 결측인데 기존 imputer가
열을 제거해 model fit 전에 중단됐다. 결과·metric·산출물은 생성되지 않았다. DEC-101에 따라
20개 Feature 순서를 유지하고 train-all-missing Feature를 imputer 0과 계수 0의 zero-effect로
처리한 뒤 code/config hash를 다시 동결해 실행했다. C와 D의 필수 입력이 전부 결측이면
계속 fail-closed한다.

## 4. 동결 무결성

- model-state hash: `034142db1930c0ec9d9f201bc2e58b68026b897100066d88c0d27c24391cf78a`
- bundle SHA-256: `da9b8111c3c9c59126746075bc019a5218d33c0259a1c22d0eea00ea3cd3c550`
- artifact tree SHA-256: `2cb97749c42406bd36d088b8504226a6b86296230ef51a316000156343a813e1`
- manifest SHA-256: `08bb74b3319a77af8ecc2f1426cb8cde07bc2f68ef44d1f860dde7e83716f6dc`
- code hash: `302a3de4fdb8edfab5aeec3dd53d83bdc2b83ce065a9c607cf5664f8cf43e3a0`
- config hash: `2e3d0a76e03559bc099b87d28de8ea87bc682af740802a6b03d24330e57f31a8`
- data version: `48bfe350aa67a2ef677607771e92135f7b921f011b6d485925478562cb5fef2c`
- primary/reproduction 필수 파일: `11/11` byte-identical

sklearn estimator를 reload한 뒤 다시 pickle한 bytes는 객체 identity와 memoization 때문에
권위 해시로 쓰지 않는다. exact bundle·manifest·artifact tree SHA, runtime versions map,
Feature 이름·순서와 고정 probe prediction을 무결성 계약으로 사용한다.

## 5. 판정

- 당시 계산: `phase4e_model_gate_pass=true`, primary `C_ONLY`
- 후속 최종 decision: `SUPERSEDED_PHASE4E_LABEL_INTEGRITY`
- `phase5r_predict_only_diagnostic_allowed=false`

기존 bundle을 사용한 Phase 5R predict나 성과 평가는 금지한다. 새 Experiment ID에서 모든
20% 이상 연속세션 주식수 변화를 candidate-only 경계로 삼아 라벨과 기술 Feature history를
초기화하고, OOF 전체를 다시 학습·선택해야 한다.

## 6. 산출물

- 본 실행: `artifacts/v2_phase4e_ai_model/`
- 독립 재현: `artifacts/v2_phase4e_ai_model_reproduction/`
- 설정: `configs/v2_phase4e_ai_model.json`
- 명세: `docs/stages/v2_phase_4e_spec.md`
- registry: `experiments/registry.csv`의 `EXP-20260901-001`

## Codex Handoff

- 역사 고정 입력: superseded Phase 4E bundle·manifest·artifact tree·model-state·runtime·Feature
  contract hash. 이 파일은 오류 증거 보존용이며 predict 입력이 아니다.
- 허용 작업: 새 Experiment ID에서 DEC-105 candidate-only 경계, 라벨 무효화, 기술 Feature
  reset을 구현하고 B/C/D OOF 전체를 재학습·재선택한다.
- 금지 작업: 기존 bundle 재사용, 2019~2020 결과에 맞춘 Feature·threshold 조정, 포트폴리오
  성과를 새 Phase 4 선택 근거로 추가, protected OOS 접근.
- Phase 5 재개 전 조건: 새 Phase 4 primary/reproduction·hash·라벨 감사를 통과한 bundle을
  먼저 동결한다. 이후에도 `docs/stages/v2_phase_5r_report.md`의 corporate-action·identity
  차단 사유가 남아 있으면 engine·성과 gate는 호출하지 않는다.
