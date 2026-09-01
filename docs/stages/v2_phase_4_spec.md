# v2 Phase 4 Agent D 결합·포트폴리오 사전등록 명세

## 상태

`COMPLETED_REJECTED`

Experiment ID `EXP-20260826-004`는 독립 Agent B·C 점수를 실제 매매 규칙으로
결합하는 첫 consumed-development 포트폴리오 진단이다.

## 입력

- Agent B: `EXP-20260826-001` 일별 Top 30과 펀더멘털 점수
- Agent C: `EXP-20260826-003` 전체 PIT KOSPI 200 독립 기술 점수
- KRX 일봉·상장주식수·시가총액, 2019-01-02~2023-12-28
- v2 2022~2023은 이미 소비된 개발 자료이며 OOS가 아니다.

Agent B는 종목을 제거하지 않는다. Agent C score 0.05 이상인 전체 종목이 진입
후보이며, B Top 30 해당 여부와 B 내부 순위는 결합 우선순위에만 가산한다.

## 사전등록 후보

- `C100`: B 0%, C 100%
- `B25_C75`: B 25%, C 75%
- `B50_C50`: B 50%, C 50%
- `B75_C25`: B 75%, C 25%

C는 날짜별 전체 percentile, B는 Top 30 내부 percentile이며 B 비해당 종목의 B 값은
0으로 둔다. 결과를 본 뒤 새 가중치를 추가하지 않는다.

## 매매

- t일 종가 후 score → t+1 시가 주문
- t+1 시가의 t 종가 대비 절대 gap이 5% 초과면 매수 거부
- Agent C score 0.05 이상: 목표비중 5%
- Agent C score 0.075 이상: 목표비중 11%
- 결합점수 순 최대 10종목, 최소 0종목, no pyramiding
- 진입가 대비 -5% 손절, +10% 익절, 최대 10세션
- 같은 일봉 손절·익절 동시 도달: 손절 우선
- commission 2bp/side, slippage 10bp/side, 실제 연도별 KOSPI 매도세율
- 기계적 분할·병합은 상장주식수 배수로 포지션을 먼저 조정한다.

## benchmark와 선택

공식 KOSPI 200 지수 원천이 없으므로 당시 membership의 전일 시가총액 가중
close-to-close 수익률을 누적한 `PIT_KOSPI200_CAP_WEIGHTED_PROXY`를 사용한다.

- 선택: 총 순초과수익률 최대, 동률이면 Sharpe 최대, B 가중치가 작은 후보 우선
- 승격 gate: 총 순초과수익 > 0, 연도별 순초과수익 양수 3/5 이상, Sharpe > 0,
  MDD > -30%, reconciliation PASS
- 하나라도 실패하면 거래 후보로 승격하지 않는다.

## 금지사항

- 가중치·0.05/0.075·손익비·gap·보유기간 사후 변경
- 공식 KOSPI 200 지수라고 proxy를 표현
- Final OOS, v1 Development Test 파티션, 분봉, 실주문·배포

## Codex Handoff

기존 결정론적 엔진을 사용하고, 실행시간 gap veto와 bracket 가격이 t+1 시가에서만
결정됨을 테스트한다. source·config·B/C/market hash를 실행 전에 registry에 동결한다.
