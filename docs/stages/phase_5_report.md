# Phase 5 Technical Cross-sectional Ranking Model 보고서

## 1. 결론

`EXP-20260822-001`의 Train/Validation Selection을 완료했다. 사전등록된 8개 후보 중 `tree_d3_l002`가 2019~2021 연결 Validation 기본비용 Sharpe 기준으로 선택됐다.

이 결론은 **Selection 후보 동결**이며 Phase 5 최종 채택이 아니다. Development Test는 사용자 별도 승인이 없어 입력·계산·평가·선택 모두 0행이다. Final OOS에도 접근하지 않았다.

선택 후보는 Validation 연도별 순초과수익률이 2019·2020·2021 모두 음수여서 D20의 3/3 통과 조건을 이미 실패했다. 따라서 Development Test 결과와 무관하게 모든 채택 gate를 동시에 충족할 수 없다.

## 2. 사전등록과 물리 입력

- Experiment ID: `EXP-20260822-001`
- Feature: `reversal_5` 하나
- 모델 후보: Raw Rank 1개, OLS 1개, shallow tree 6개
- seed: `20260822`
- purge/embargo: 각각 20 거래소 세션
- Train: 2011~2018부터 시작하는 anchored expanding window
- Validation: 2019, 2020, 2021 연도별 fold
- 포트폴리오: H=20, N=10, 종목당 10%, no pyramiding
- 입력 역할: `phase5_train_validation`
- 입력 최대 허용일: 2021-12-31
- 실제 최대 로드일: 2021-12-30

Phase 5 파티션은 검증 완료된 Phase 4의 2021년 이하 물리 파티션 네 파일과 Phase 3 Train/Validation 강제청산 주문 감사 자료에서 만들었다. Development Test 파티션은 만들지 않았다. 연구 runner는 manifest의 역할·날짜·행 수·bytes·SHA-256을 모두 확인한 뒤 허용된 다섯 파일만 읽는다.

## 3. 선택 결과

| 순위 | 후보 | 연결 Validation Sharpe | 순초과수익률 | 최대낙폭 |
|---:|---|---:|---:|---:|
| 1 | `tree_d3_l002` | 0.2275 | -42.4565%p | -41.3658% |
| 2 | `tree_d2_l002` / `tree_d2_l005` | 0.2178 | -43.1920%p | -42.0550% |
| 3 | `tree_d3_l005` | 0.2113 | -43.5814%p | -40.1316% |
| 4 | `tree_d1_l002` / `tree_d1_l005` | 0.1275 | -48.7334%p | -39.4996% |
| 5 | `raw_rank` / `ols` | 0.0320 | -55.3932%p | -42.6280% |

선택 모델의 연결 Validation 전략 수익률은 7.9429%, KOSPI 100 지수 수익률은 50.3994%였다. Phase 3 기준선보다 Sharpe는 0.3281 높았지만 지수를 크게 하회했다.

### 연도별 결과

| fold | 기본비용 순초과수익률 | 기본비용 Sharpe | 2배 비용 순초과수익률 |
|---|---:|---:|---:|
| 2019 | -15.1750%p | -0.0207 | -17.8688%p |
| 2020 | -10.1559%p | 0.7951 | -12.8389%p |
| 2021 | -9.6458%p | -0.5933 | -11.6944%p |

연도별 순초과수익률 0 이상 fold는 0/3이다. D20은 3/3을 요구하므로 Validation gate는 실패다.

### 순위 예측 진단

| fold | 평균 일별 Spearman IC | NDCG@10 | 상·하위 decile target spread | coverage |
|---|---:|---:|---:|---:|
| 2019 | 0.00726 | 0.5281 | 0.01228 | 1.0 |
| 2020 | 0.04092 | 0.5434 | 0.04416 | 1.0 |
| 2021 | 0.01776 | 0.5320 | 0.02585 | 1.0 |

약한 양의 순위 관계는 세 fold에서 관찰됐지만, 비용 차감 상대성과로 이어지지 않았다.

## 4. 사용 변수와 관계

입력 변수는 `reversal_5` 하나다.

```text
reversal_5 = -(오늘 종가 / 5거래일 전 종가 - 1)
```

최근 5일에 많이 하락한 종목일수록 값이 커지고, 많이 오른 종목일수록 값이 작아진다. 매일 KOSPI 100 구성종목 안에서 이 값을 0~1 순위로 바꾼다.

`tree_d3_l002`는 이 순위 하나를 최대 세 번 나누어 향후 10거래일 초과수익률 순위를 예측한다. 즉 여러 변수를 결합한 모델이 아니라, **최근 5일 하락 정도와 이후 상대수익률의 관계가 직선이 아닐 수 있음**을 몇 개 구간으로 표현한 모델이다. 최소 leaf 2%는 아주 작은 일부 종목만 보고 구간을 만들지 못하게 제한한다.

## 5. 비용 stress

연결 Validation에서 2배 비용 Sharpe는 0.1149, 순초과수익률은 -50.0434%p였다. 3배 비용 Sharpe는 -0.0026, 순초과수익률은 -57.5329%p였다. 세금은 stress에서도 제거하지 않았다.

## 6. 감사와 재현성

- source hash: `1600bcd361ce90e0a7f56500fd1d74393e8123ca851f002f438f7a60e158c240`
- config hash: `e3ea32fa995e3302539b8a28ed7193c7e7ccb1cc2af7dea76d6dc3ba6ef1fb21`
- data hash: `d4b817519bc7b9956b26bbc8e099356a0b1b3cb4e402674b59e93a1525162417`
- 후보 모델군 hash: `e45ee94e6f798c9e5be4fda944c779a5889ef0ce28d03213b2a6fa05fc01bd87`
- 선택 모델 hash: `822ebea85b8c9745e3bfa5718d48ba0a383b5017298542a91184cc2e0bf54923`
- dependency hash: `2e343fa4ec97652567f2231f4878c130d33f357ca2509f257ac4c87e6cde9b83`
- Python 3.14.7, pandas 2.3.3, NumPy 2.5.2, scikit-learn 1.9.0
- Selection과 독립 재실행의 8개 파일: 모두 byte-identical
- Development Test loaded/calculated/evaluated/selected: 모두 0
- 로드 후 날짜 필터: false
- Final OOS 접근: false

첫 계산 뒤 CLI의 `date` 콘솔 직렬화 오류를 발견해 출력 계층만 수정했다. 다음 결과 감사에서 tree 점수 동률 때문에 decile spread가 비어 있음을 발견해, 포트폴리오와 같은 `score 내림차순, security_id 오름차순` 동률 규칙으로 필수 진단 지표를 보완했다. 두 수정은 Feature, target, fold, 후보, 비용, 포트폴리오, 선택 우선순위나 선택 결과를 바꾸지 않았다.

## 7. 테스트

- Phase 5 전용: 12/12 PASS
- 전체 회귀: 62/62 PASS
- manifest 경계 위반을 모든 데이터 파일 접근 전에 거부: PASS
- purge/embargo 20 세션: PASS
- 8개 후보의 Train-only fit 및 결정성: PASS
- t일 신호에서 다음 세션 주문: PASS
- 독립 실제 재실행 byte determinism: PASS

## 8. 미결정 사항

사용자 별도 결정이 필요하다.

1. 명세대로 동결 모델의 Development Test를 한 번 공개할지
2. 이미 확인된 Validation gate 실패를 근거로 Development Test를 쓰지 않고 `rejected`를 확정할지

어느 경우에도 모델·Feature·비용·포트폴리오·gate를 바꾸지 않는다.

## Codex Handoff

- 동결 후보: `tree_d3_l002`
- 동결 선택 산출물: `artifacts/phase5/selection/`
- 현재 상태: `selection_completed`, Development Test 미승인
- 다음 명령은 사용자 별도 승인 전 실행 금지: `confirm-development-test`
- Phase 6 명세나 실행을 시작하지 않는다.
