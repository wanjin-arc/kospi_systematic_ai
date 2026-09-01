# v2 Phase 5S 동결 모델 Predict-only 무결성 감사 실행 보고서

## 1. 실행 결론

- Experiment ID: `EXP-20260901-004`
- 설정: `configs/v2_phase5s_share_change_safe_integrity.json`
- 입력 모델: `EXP-20260901-003` Phase 4F `C_ONLY`
- 평가 기간: 2021~2023 소비 개발자료
- 실행 모드: `PREDICT_AND_PRE_EXECUTION_INTEGRITY_AUDIT`
- 최종 결정: `REJECT_PHASE5S_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`
- 증거 지위: 소비 개발자료 기반 predict-only 진단이며 OOS가 아니다.

Phase 5S는 Phase 4F 동결 모델을 재학습 없이 적용해 점수와 차단된 주문 의도를 생성했다. 그러나
stable identity와 Corporate Action 권리조건이 완전하지 않아 portfolio accounting 직전에
fail-closed 했다. 따라서 이 실험은 Phase 5 성과 실험이 아니며, 전략 수익률·지수 대비 성과·MDD
등 어떤 경제 성과도 평가하지 않았다.

## 2. Predict-only 실행 결과

| 항목 | 실행 결과 |
|---|---:|
| 전체 score panel | 931,658행 |
| 2021~2023 예측 점수 | 141,782행 |
| 재조정 시점 | 36회 |
| 차단된 주문 의도 | 3,600건 |
| 전략 주문 의도 | 1,800건 |
| neutral core 주문 의도 | 1,800건 |
| fit 호출 | 0회 |
| portfolio engine 호출 | 0회 |
| 성과 metric 관측 | 0건 |
| 실행 가능한 Corporate Action | 0건 |
| 외부 주문 제출 | 0건 |
| protected OOS 접근 | 0건 |

3,600건은 모두 `BLOCKED_NOT_SUBMITTED` 상태의 감사용 주문 의도다. 보유 수량을 만들거나
체결·계좌·NAV에 반영한 주문이 아니다. 삼성전자 `005930`과 SK하이닉스 `000660`은 점수·순위·
liquidity core·주문 의도에서 제외했다.

## 3. 주식수 후보와 identity 감사

상장주식수 후보는 같은 exact raw ticker의 연속 거래일 상장주식수 gross ratio가 `1.20` 이상인
경우로 한정했으며 가격을 사용하지 않았다. 후보는 경계 진단일 뿐 실행 가능한 권리행사가 아니다.

| 감사 항목 | 결과 |
|---|---:|
| 평가구간 주식수 변화 후보 | 86건 |
| 전일·당일 모두 PIT 구성종목인 후보 | 37건 |
| 원천 exact raw ticker 후보 | 223건 |
| 원천 비정규 ticker 행 | 15,490행 |
| 원천 ticker 정규화 충돌 | 4건 |
| membership ticker 정규화 충돌 | 0건 |
| 상장주식수 관측 공백 행 | 0행 |

원천 market 자료의 정규화 충돌 4건은 다음과 같다.

- `000680` ← `000680`, `00680K`
- `033626` ← `33626K`, `33626L`
- `033637` ← `33637K`, `33637L`
- `037550` ← `37550K`, `37550L`

membership 자체에는 정규화 충돌이 없었지만, market 원천에는 비정규 ticker 15,490행과 위 충돌이
있었다. 또한 `KRX_COMMON:<normalized_ticker>` 구성은 역사적 issuer/share-class/successor 관계를
해결한 identity가 아니다. 이에 따라 `canonical_raw_ticker_contract_complete=false`,
`stable_identity_contract_complete=false`, `position_accounting_allowed=false`로 판정했다.

## 4. 실행 전 무결성 gate

| 무결성 gate | 결과 |
|---|---|
| Phase 4F model gate | `true` |
| stable identity contract 완전성 | `false` |
| Corporate Action terms 완전성 | `false` |
| canonical EX2 return 평가 가능성 | `false` |

Phase 4F 모델 자체는 허용됐지만 나머지 세 조건이 충족되지 않았다. 특히 37개 ambiguous event/date의
일별 최대 사전 비중은 `0.03722067470667447`이었다. 이는 포트폴리오 회계에서 무시할 수 있다고
사전 선언된 0이 아니며, 권리조건을 임의로 추정할 근거도 아니다.

`ex2_price_unit_sensitivity.csv`와 `ex2_issuer_cap_value_sensitivity.csv`는 모두 비자기금융 진단이다.
두 파일은 return, 상·하한, benchmark 또는 경제 gate가 아니며, 공식 KRX 1028 reference 역시
동기화 점검용으로만 생성했다.

## 5. 성과는 미평가

다음 항목을 포함한 모든 사전등록 경제 gate는
`NOT_EVALUATED_PRE_EXECUTION_INTEGRITY_BLOCK`이다.

- neutral core 대비 순초과수익과 rolling 12개월 shortfall
- MDD와 neutral core 대비 MDD shortfall
- EX2 대비 연환산 초과수익과 downside capture
- 공식 KRX 1028 대비 최악 연도와 최악 rolling 12개월
- 평균 주식 노출, 청산 거래 수, 기본비용 및 비용 stress

따라서 70% 동일가중 liquidity core + 20% C alpha tilt + 10% 현금 구조가 우수하거나 열등하다는
결론도 내릴 수 없다. `phase5_gate_pass=false`는 수익률 gate를 계산해 실패했다는 뜻이 아니라,
그 전에 identity/Corporate Action 무결성 계약이 불완전하여 평가 자체가 차단됐다는 뜻이다.

## 6. 해시와 재현성

| 대상 | SHA-256 |
|---|---|
| Phase 4F model | `b558ecbfba2fd5022cb12f10c5df2499559642e4f5b4f1e9f781c223e7a41e4f` |
| Phase 4F bundle | `47f10289d6c25ab7dbcb73d6429dbef0208b872d6ca0d12f770827cb23fa9792` |
| Phase 4F artifact tree | `2f85ddff15bc2850f16ca29e0b9b3e50357a59702c8c5154afd2db39c1e7a33d` |
| Phase 4F manifest | `3bff178aa629421f29341c7af5aa4fafcb877cf1e30a9e92e91485bbfddd4b69` |
| Phase 5S code | `e9118fdac9d738f08d4d94aa8ee85d318c658cc66b647e9d22f5817cdbca9a58` |
| Phase 5S config | `f42b6020954563b9087427e13436a3272ece064193218b8bde8397f6a251e599` |
| Phase 5S data version | `6fd9f21ea735a8458ed2fa07bd19e45290f111a5af82a70e83914f32166d3ba0` |
| Phase 5S manifest | `70b55b6782e3f3f7bfa4699467d222240a1a7da9589635b611a361c13e5e4693` |

primary와 reproduction의 필수 산출물 10개는 10/10 byte-identical이었다. Phase 4F의
model/bundle/tree/manifest hash도 모두 입력 계약과 일치했다.

주요 산출물은 다음 위치에 있다.

- primary: `artifacts/v2_phase5s_share_change_safe_integrity/`
- reproduction: `artifacts/v2_phase5s_share_change_safe_integrity_reproduction/`
- 점수와 차단 의도: `scores.csv.gz`, `order_intents_blocked.csv`
- 후보·identity 감사: `share_reset_candidates.csv`, `audit.json`
- EX2 진단: `ex2_share_reset_events.csv`, `ex2_price_unit_sensitivity.csv`,
  `ex2_issuer_cap_value_sensitivity.csv`, `official_krx1028_reference.csv`
- 결정·재현 계약: `decision.json`, `manifest.json`

재현 명령은 다음과 같다.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m kospi200_phase5s.cli preflight --config configs/v2_phase5s_share_change_safe_integrity.json
.\.venv\Scripts\python.exe -m kospi200_phase5s.cli run --config configs/v2_phase5s_share_change_safe_integrity.json --output artifacts/v2_phase5s_share_change_safe_integrity_reproduction
```

## 7. 문제와 한계

1. market 원천의 비정규 ticker와 정규화 충돌 때문에 exact raw ticker audit만으로 canonical
   security identity를 만들 수 없다.
2. 역사적 issuer, share class, 종목코드 변경, 분할·합병 후 successor 관계가 PIT 기준으로
   완성되지 않았다.
3. 주식수 변화 후보마다 권리 유형, 비율, old-holder 권리, 효력 거래일과 cash-in-lieu 조건이
   확정되지 않았다.
4. EX2 두 sensitivity는 자기금융 포트폴리오가 아니므로 성과나 가능한 수익률 범위로 읽을 수 없다.
5. 2021~2023은 이미 소비된 개발자료이므로 이 기간에서 모델·threshold·포트폴리오 규칙을 다시
   조정하면 추가 과적합만 늘어난다.

## 8. 다음 단계 조건

Phase 5의 경제 평가를 새로 시작하려면 다음을 먼저 갖춰야 한다.

1. 거래일별 PIT issuer/share-class/successor stable identity map
2. 모든 1.20 gross-ratio 후보의 권리 유형, 확정 비율, old-holder 조건, 효력 거래일
3. 가격·상장주식수·권리자료의 동일 비율 교차검증과 예외의 fail-closed 처리
4. 자기금융 position accounting과 cash-in-lieu·강제청산 규칙
5. 위 계약의 독립 테스트와 primary/reproduction byte 재현성
6. 새 Experiment ID, 결과 관측 전 registry/hash 동결, 사용자 승인

계약을 완성해도 2021~2023을 재튜닝 구간으로 되돌리지 않는다. 동결된 구조의 독립 성과 증거는
새 forward shadow에서 축적하고, protected OOS는 Phase 8 단일 릴리스 승인 전까지 접근하지 않는다.

## Codex Handoff

- `EXP-20260901-004`는
  `REJECT_PHASE5S_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`로 종료한다.
- 현 산출물은 점수·후보·차단 주문 의도·identity/EX2 진단 증거로만 보존한다. NAV, return,
  bound, benchmark 성과 또는 경제 gate로 승격하지 않는다.
- 완료 조건인 Phase 4F hash 일치, fit/engine/performance/action/external order/OOS 0,
  모든 주문 의도 차단, 10/10 byte 동일성은 충족했다. 이는 Phase 5 성과 통과가 아니라
  predict-only 무결성 감사 완료를 뜻한다.
- 후속 구현은 stable identity와 Corporate Action terms를 별도 데이터 계약으로 완성하고 테스트한
  뒤 새 사전등록 실험에서만 수행한다.
- protected OOS 접근, 실제 주문, 기존 2021~2023 결과 기반 재튜닝은 계속 금지한다.
