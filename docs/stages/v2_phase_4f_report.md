# v2 Phase 4F 주식수 경계 안전 AI 모델 실행 보고서

## 1. 실행 결론

- Experiment ID: `EXP-20260901-003`
- 설정: `configs/v2_phase4f_share_change_safe_model.json`
- 증거 기간: 2004~2020 소비 개발자료
- 선택 모델: `C_ONLY`
- 최종 결정: `FREEZE_MODEL_FOR_PHASE5S_CONSUMED_DIAGNOSTIC`
- model gate: `true`
- 증거 지위: 소비 개발자료 기반 모델 진단이며 독립 OOS 또는 거래 성과 증거가 아니다.

Phase 4F는 `EXP-20260901-001` Phase 4E의 라벨 경계 오류를 수정한 새 실험이다. 같은 exact raw
6자리 ticker의 연속 거래일 상장주식수만 비교하여 gross ratio `1.20` 이상 변화를
`UNRESOLVED_SHARE_CHANGE_CANDIDATE`로 표시했고, 그 경계를 가로지르는 라벨을 제거하는 동시에
기술 Feature segment를 초기화했다. 가격은 후보 판정에 쓰지 않았으며 후보를 실행 가능한
Corporate Action으로 해석하지 않았다.

사전등록한 B/C/D 후보 가운데 `C_ONLY`가 가장 높은 평균 Rank IC를 기록했다. `D_SOFT_FUSION`은
최선 단일 모델인 C보다 엄격하게 개선되지 않아 선택되지 않았다. 따라서 이 결과는 B→C→D
직렬 필터가 아니라 B와 C의 독립 점수를 D가 soft fusion하는 구조에서 C 단독을 선택한 것이다.

## 2. 데이터와 경계 감사

| 항목 | 실행 결과 |
|---|---:|
| 전체 score panel | 789,876행 |
| OOF/선택용 표본 | 23,722행 |
| 최종 유효 fit 라벨 | 23,190행 |
| 주식수 변화 후보 경계를 가로질러 제외한 라벨 | 88행 |
| 상장주식수 관측 공백 행 | 0행 |
| 유효 fit 라벨의 주식수 변화 경계 통과 | 0행 |
| 유효 fit 라벨의 상장주식수 관측 공백 통과 | 0행 |
| 유효 Selection 라벨의 경계 통과 | 0행 |
| 기술 Feature의 경계 이전 이력 누출 | 0행 |

라벨 가용성은 score Universe 구성에 사용하지 않았고, 경계 제거 전후 score Universe는
변하지 않았다. 삼성전자 `005930`과 SK하이닉스 `000660`은 사전등록대로 학습·평가·점수·순위
후보에서 제외했다. 최종 fit signal 최대일은 `2020-11-27`, label exit 최대일은
`2020-12-29`, 입력 최대일은 `2020-12-30`이다. 2021년 이후 자료를 fit에 사용하지 않았고
protected OOS 접근은 없었다.

## 3. 모델 선택 결과

| 후보 | 평균 Rank IC | 비음수 연도 | 평균 Top10 target quality | 판정 |
|---|---:|---:|---:|---|
| `B_ONLY` | -0.00448697557122 | 1/2 | -0.0655894870305 | 탈락 |
| `C_ONLY` | 0.0178096035776 | 1/2 | -0.0525263490945 | 선택 |
| `D_SOFT_FUSION` | 0.0171870579868 | 1/2 | -0.0525369477294 | C 대비 엄격한 개선 없음 |

`C_ONLY`의 Selection 연도별 Rank IC는 2019년 `-0.0115764338597`, 2020년
`0.0471956410149`였다. 평균 Rank IC가 0보다 크고 사전등록한 2개 연도 중 최소 1개가
비음수라는 모델 게이트를 충족하여 `model gate=true`가 되었다.

다만 양의 성과가 두 연도에 일관되지 않았고 평균 Top10 target quality도
`-0.0525263490945`로 음수다. 따라서 model gate 통과는 Phase 5S predict-only 무결성 진단에
사용할 모델을 동결했다는 뜻일 뿐, 포트폴리오 유효성이나 지수 대비 성과를 인정한 것이 아니다.

## 4. 생성 모델과 재현성

동결된 핵심 hash는 다음과 같다.

| 대상 | SHA-256 |
|---|---|
| model | `b558ecbfba2fd5022cb12f10c5df2499559642e4f5b4f1e9f781c223e7a41e4f` |
| bundle | `47f10289d6c25ab7dbcb73d6429dbef0208b872d6ca0d12f770827cb23fa9792` |
| artifact tree | `2f85ddff15bc2850f16ca29e0b9b3e50357a59702c8c5154afd2db39c1e7a33d` |
| manifest | `3bff178aa629421f29341c7af5aa4fafcb877cf1e30a9e92e91485bbfddd4b69` |
| code | `d604a358876652fdbb8b51067230ac28a956b04d256e7000de30015c37398c6e` |
| config | `c49cb1d1f13ee082ee2fa508c5120c7d937395c92d2ac67b5e430ad12b563b49` |
| data version | `b1ae5a7e148eccf79181fa92745eaee6ce1c00d99cd2d93b038e37974d2c245a` |

primary와 reproduction 산출물의 필수 파일 11개는 11/11 byte-identical이었다. 실행 runtime은
Python 3.14.7, NumPy 2.5.2, pandas 2.3.3, SciPy 1.18.1,
scikit-learn 1.9.0으로 manifest에 고정했다.

주요 산출물은 다음 위치에 있다.

- primary: `artifacts/v2_phase4f_share_change_safe_model/`
- reproduction: `artifacts/v2_phase4f_share_change_safe_model_reproduction/`
- 동결 모델: `frozen_model_bundle.pkl`
- 선택 결과: `selection_metrics.csv`, `selected_primary.json`, `decision.json`
- 경계 감사: `label_audit.json`, `audit.json`, `feature_contract.json`
- 재현 계약: `component_hashes.json`, `fold_boundaries.json`, `manifest.json`

재현 명령은 다음과 같다.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m kospi200_phase4f.cli preflight --config configs/v2_phase4f_share_change_safe_model.json
.\.venv\Scripts\python.exe -m kospi200_phase4f.cli run --config configs/v2_phase4f_share_change_safe_model.json --output artifacts/v2_phase4f_share_change_safe_model_reproduction
```

## 5. 금지 작업과 비실행 확인

- 포트폴리오 계산: 미실행
- 주문 의도 생성: 0건
- 실제 주문 또는 외부 주문 제출: 0건
- 실행 가능한 Corporate Action 생성: 0건
- 2021년 이후 fit: 0건
- protected OOS 접근: 0건

Phase 4F는 명세대로 model-only 단계다. 이 단계에서는 70/20/10 포트폴리오, NAV, 수익률,
MDD, turnover 또는 경제 gate를 계산하지 않았다.

## 6. 문제와 한계

1. C의 평균 Rank IC는 양수지만 2019년은 음수이고 비음수 연도는 1/2에 그쳤다.
2. Top10 target quality가 음수이므로 상위 점수 종목이 경제적으로 우수하다는 증거는 약하다.
3. 2004~2020과 2021~2023은 이미 소비된 개발기간이므로 이 결과를 독립 OOS 성과로 해석할 수 없다.
4. gross ratio `1.20`은 라벨·기술 이력의 안전 경계일 뿐, 권리 유형·비율·효력일·승계 관계를
   확정하지 않는다.
5. exact ticker 기반 `KRX_COMMON:<ticker>`는 영구 issuer/share-class identity를 증명하지 않으므로
   포지션 회계의 충분조건이 아니다.

## 7. 다음 단계 조건

Phase 4F 모델은 해시를 바꾸지 않는 predict-only 소비 개발 진단에만 사용할 수 있다. 다음 단계가
포트폴리오 엔진이나 성과 계산으로 넘어가려면 먼저 PIT stable issuer/share-class/successor identity,
권리별 old-holder 조건과 비율, 확정 효력 거래일, KRX 가격·상장주식수 교차검증을 갖춰야 한다.
이 조건을 보완할 때에는 새 Experiment ID와 새 사전등록 명세가 필요하며, 2021~2023 결과를 보고
모델·Feature·임계값을 재조정해서는 안 된다. 독립 성과 증거는 동결 이후의 새 forward shadow에서
축적해야 한다.

## Codex Handoff

- 후속 소비자는 `EXP-20260901-004` Phase 5S이며, 위 model/bundle/tree/manifest hash를 모두
  검증한 뒤 `C_ONLY`를 predict-only로 호출한다.
- Phase 5S에서 fit, scaler/imputer 재적합, Feature 선택, threshold 조정은 금지한다.
- Phase 5S는 점수와 `BLOCKED_NOT_SUBMITTED` 주문 의도까지만 만들고, stable identity와
  Corporate Action terms가 완전하지 않으면 engine import·portfolio accounting·성과 계산 전에
  fail-closed 해야 한다.
- Phase 4F의 완료 조건은 model gate 판정, 경계 누출 0, 비실행 항목 0, protected OOS 미접근,
  primary/reproduction 11/11 동일성이다. 이 조건은 모두 충족했다.
- 후속 경제 평가를 허용하려면 identity/Corporate Action 계약을 완성해 별도 실험으로
  사전등록하고 사용자 승인을 받아야 한다.
