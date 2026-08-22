# Phase 4B 다변수 기술 신호 실행 보고서

## 1. 결론

`EXP-20260823-001`은 2018년 이하 물리 파티션과 2011~2018 Train 내부 fold만 사용해 완료했다. 21개 종목 기술변수는 모두 최소 coverage 0.95를 통과해 Phase 5B joint-model 입력으로 전달했다. 이는 기존 Phase 4의 단변량 채택 판정을 소급 변경하는 것이 아니다.

Development Test와 Final OOS는 로드·계산·평가·선택하지 않았다. 2019~2021도 새 연구 runner에서 0행 로드·계산·평가·선택했다.

## 2. 물리 데이터 경계

- 연구 파티션: `data/processed/v24/phase4b_train_internal_2018/`
- 역할: `phase4b_train_internal`
- data hash: `5191493236aa5613f72700f7ac3a24403989ce80d8b2cc4ecd0b3ab913742f35`
- 최대 로드일: 2018-12-28
- 최대 연구 신호일: 2018-12-12
- 2019~2021 연구 runner 로드 행: 0
- Development Test 로드·계산·평가·선택 행: 모두 0
- Final OOS 접근: false

파티션 builder는 검증된 2021년 이하 Selection 파티션을 원천으로 스캔하고 2018년 이후 행을 별도 파생 파티션에서 제외했다. 이 upstream 스캔 사실은 `partition.json`의 `builder_audit`에 파일별 원천 행 수·원천 최대일·제외 행 수로 남겼다. 연구 runner는 생성된 2018년 이하 파티션만 읽었다.

## 3. 주요 Feature 진단

2015~2018 내부 Validation 평균 일별 Spearman IC 기준 주요 양의 관계는 다음과 같다.

| 변수 | 평균 IC | 양의 연도 |
|---|---:|---:|
| `low_atr_20` | 0.03386 | 4/4 |
| `low_volatility_20` | 0.03152 | 4/4 |
| `low_downside_volatility_20` | 0.01916 | 4/4 |
| `reversal_5` | 0.01692 | 4/4 |

주요 음의 관계는 다음과 같다.

| 변수 | 평균 IC | 양의 연도 |
|---|---:|---:|
| `risk_adjusted_momentum_63` | -0.03051 | 0/4 |
| `momentum_63` | -0.02910 | 1/4 |
| `excess_momentum_63` | -0.02910 | 1/4 |
| `trend_sma20_sma60` | -0.02796 | 1/4 |

따라서 고정된 양의 가중합보다 Train-only regularization 또는 제한된 비선형 모델로 부호와 상호작용을 학습할 필요가 있다는 진단을 얻었다. 그러나 이 IC는 진단 지표이며 거래 후보 채택 근거가 아니다.

## 4. 기존 Phase 5 부진 원인 진단

- `reversal_5` 하나만 사용해 모든 후보가 같은 1차원 정보의 변환이었다.
- 평균 Rank IC가 약해 실제 비용 차감 성과로 충분히 이어지지 않았다.
- 10세션 target과 20세션 보유가 불일치했다.
- 평균 약 20% 현금과 거래비용이 강한 상승장에서 지수 대비 불리했다.

Phase 5B에서는 21개 종목변수, 5개 시장상태, 6개 고정 상호작용과 10세션 보유를 사전등록했다.

## 5. 재현성과 검증

- source hash: `71708ec32b6b801043d3d34dd00a61ddfd8c88669f769d18bc8a5d70076e3969`
- config hash: `6d27185309682407ce67ee9458f5da34a5c2d0ac34c387e402bd9a6f8ed51717`
- manifest SHA-256: `b907a2cff2c3818b7abc18db93d2b3222ec791b394cfc6d5e37a66f2b7e8b453`
- 독립 재실행 6개 파일: 모두 byte-identical
- Phase 4B/5B 신규 테스트: 10/10 PASS
- 전체 회귀 테스트: 72/72 PASS

## Codex Handoff

- Phase 4B 상태: 완료
- 인계 Feature: 설정에 고정된 21개 종목변수, 5개 시장상태, 6개 상호작용
- 산출물: `artifacts/phase4b_multifactor/`
- 다음 단계: 동결된 `EXP-20260823-002` Phase 5B 결과를 따른다.
- 금지: 기존 Phase 4 단변량 판정 변경, 2019~2021 재최적화, Development Test·Final OOS 접근
