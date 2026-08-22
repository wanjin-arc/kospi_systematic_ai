# Phase 5G 다중 기간 합의 모델 보고서

## 결론

`EXP-20260823-007`은 구현·실행·독립 재실행까지 완료했으나 내부 gate를 통과하지 못했다. 모델은 거래 후보와 Development Test 후보가 아니다. 2019년 이후 데이터, Development Test, Final OOS는 접근하지 않았다.

2015~2018 연결 내부 진단에서 전략 수익률은 +3.72499%, KOSPI 100은 +7.38474%, 순초과수익률은 -3.65975%p였다. 2배 비용에서는 -6.95930%p였다. 연도별 순초과수익률은 2015년 +6.38472%p, 2016년 -10.28764%p, 2017년 -27.34413%p, 2018년 +22.11338%p로 2/4만 비음수였다.

## 사용한 변수와 관계

- 종목 변수 21개는 반전, 중·장기 모멘텀, 지수 대비 모멘텀, 이동평균 추세, 52주 고저점 위치, 변동성·하방위험·ATR, 거래량·거래대금 확인, 유동성·비유동성을 표현한다.
- 시장 변수 5개는 KOSPI 100 장기추세·63일 모멘텀·저변동성과 구성종목 breadth 두 종류를 표현한다.
- 상호작용 6개는 같은 종목 신호라도 시장 추세·breadth·변동성 환경에 따라 의미가 달라질 수 있도록 연결한다.
- Extra Trees는 이 32개 입력을 이용해 5·10·20거래일 비용 차감 초과수익을 동시에 예측한다. 세 기간 중 둘 이상이 양수이고 예측 중앙값이 0.2% 이상인 종목만 매수 대상으로 삼고, 중앙값으로 매일 순위를 정한다.

이 구조는 “매일 전 종목 점수 → 합의 조건 → 순위 → 다음 날 주문”이라는 목표 구조를 구현한다. 최소 보유 수는 없어서 조건을 만족하는 종목이 없으면 현금으로 남는다.

## 진단 결과

| 항목 | 결과 | gate |
|---|---:|---|
| 연결 전략 수익률 | +3.72499% | 참고 |
| 연결 지수 수익률 | +7.38474% | 참고 |
| 연결 순초과수익률 | -3.65975%p | 실패 |
| 2배 비용 순초과수익률 | -6.95930%p | 실패 |
| 연도별 비음수 fold | 2/4 | 실패, 4/4 필요 |
| 최대낙폭 | -18.33549% | 통과 |
| 지수 최대낙폭 | -24.03641% | 참고 |
| 평균 현금 비중 | 83.60028% | hard gate 아님 |
| 평균 보유 종목 | 1.7737개 | 최소 보유 0개 |
| 진입 주문 / 체결 | 1,324 / 304 | 활동성 통과 |

기간별 예측 Spearman은 2015·2018년에 대체로 양수였고 2017년에 세 기간 모두 음수였다. 즉, 여러 기간의 방향 합의가 단일 기간 노이즈는 일부 줄였지만 시장 국면 전환에 대한 안정성은 확보하지 못했다. 단순히 현금 비중이나 최소 보유 수가 문제라기보다 2016~2017의 종목 상대·절대 성과 관계가 학습 구간과 달라진 것이 핵심 실패 원인이다.

같은 2015~2018에서 수행한 Phase 5B의 연결 순초과수익률 -11.5013%p보다는 손실 폭이 줄었지만, 이는 수용 기준을 충족한다는 뜻이 아니다. 현재 구간을 다시 보고 threshold·tree 깊이·Feature 조합을 바꾸면 내부 구간 과최적화가 된다.

## 데이터·재현성 감사

- 물리 파티션 역할: `phase4b_train_internal`
- 최대 로드일: 2018-12-28
- 최대 연구 신호일: 2018-11-28
- 2019년 이후 loaded/calculated/evaluated/selected: 모두 0
- Development Test loaded/calculated/evaluated/selected: 모두 0
- Final OOS 접근: false
- 로드 후 날짜 필터: false
- source hash: `a6825fd4e230546faf9697c2120a821dbb7bde0f31c622bcbf215a0b5393bb65`
- config hash: `af1fa30ab2f1b1186530c71d0d9d74e2764aab1150bbf773bd70436bad871ff1`
- data hash: `5191493236aa5613f72700f7ac3a24403989ce80d8b2cc4ecd0b3ab913742f35`
- model contract hash: `64e9eec7d94e044ac25b8f80c9f638f168cb8558b6cdd802d67d48bbd8c50436`
- 산출물 11개 독립 재실행: 모두 byte-identical
- manifest SHA-256: `a8c005cf9e658be69cc03594822452c53377c1ce77957a9eda24f2674dd280c9`

## 테스트와 남은 조건

- Phase 5G 전용 테스트: 10/10 PASS
- 전체 회귀 테스트: 118/118 PASS
- t 종가 → t+1 시가 → t+6·t+11·t+21 시가, 비용, PIT reset·tradable, Train-only 적합, purge/embargo, 매일 순위, 다음 세션 주문, 미래 점수 불변성을 검증했다.

현재 데이터에서 같은 검증 구간을 사용하는 추가 모델 생성은 중단한다. 다음 유효한 연구는 사용자가 제공할 2008년 이전 KOSPI 100 또는 외부 시장의 별도 물리 데이터로 시간축을 확장해, 새로운 Experiment ID와 독립 검증 구간을 먼저 고정한 뒤 진행해야 한다. 추가 데이터가 도착하기 전에는 수용 판정을 만들 수 없다.

## Codex Handoff

- 구현: `src/kospi100_multihorizon/`
- 설정: `configs/phase5g_multihorizon_consensus.json`
- 산출물: `artifacts/phase5g/internal_diagnostic/`
- 재현: `PYTHONPATH=src python -m kospi100_multihorizon.cli run --config configs/phase5g_multihorizon_consensus.json --output <새 출력 경로>`
- 현재 결정: `reject_internal_consensus_no_promotion`
- 다음 허용 작업: 새 데이터의 출처·PIT Universe·Corporate Action·거래일 품질 감사와 물리 Train/Validation 파티션 설계.
- 금지: 같은 2015~2018 결과 기반 재조정, 2019~2021 재사용, Development Test 또는 Final OOS 접근.
