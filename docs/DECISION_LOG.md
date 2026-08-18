# Decision Log

## Use Rules

- IDs are permanent and monotonic: `DEC-YYYY-###`.
- Do not edit a decided value to match a later result. Add a superseding decision that names the previous ID, reason, expected impact, and whether final OOS is invalidated.
- `Confirmed` means approved for the stated stage; `Pending verification` means the policy is fixed but its external/input fact must be audited.
- Detailed recommendation, reason, alternative, and impact for Phase-0 decisions are in `docs/RESEARCH_PROTOCOL.md` D01–D24.

## Phase-0 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-001 | Research window | 2011-01-01 to 2025-12-31; 2026 reserved for paper/live shadow | Pending verification | — |
| DEC-2026-002 | Universe | Point-in-time KOSPI 100 memberships, effective-date governed | Pending verification | — |
| DEC-2026-003 | Price convention | Raw execution series plus as-of split-adjusted feature series; no dividend-adjusted feature series | Pending verification | — |
| DEC-2026-004 | Signal time | Official close of `t`; freeze before `t+1` | Confirmed | — |
| DEC-2026-005 | Execution time | Next session opening auction/session with adverse slippage | Confirmed | — |
| DEC-2026-006 | Entry gap policy | Pre-submitted +5% marketable buy limit; no hindsight cancellation | Pending broker verification | — |
| DEC-2026-007 | Daily stop/target ambiguity | Conservative stop-first rule | Confirmed | — |
| DEC-2026-008 | Holding candidates | 5, 10, 20 trading sessions | Confirmed | — |
| DEC-2026-009 | Agent B target | 10-session cross-sectional KOSPI 100 excess open-to-open return rank; limited variants | Confirmed | — |
| DEC-2026-010 | Agent C labels | 10-session triple barrier and within-candidate excess-return label | Confirmed | — |
| DEC-2026-011 | Benchmark | KOSPI 100 price index | Pending vendor verification | — |
| DEC-2026-012 | Costs | Calendar schedule; 2 bps/side commission proxy, date-specific sale cost, 10 bps/side slippage | Pending tax/broker verification | — |
| DEC-2026-013 | Holdings | Baseline 10 slots; compare 5/10/15 only in development | Confirmed | — |
| DEC-2026-014 | Sizing | Equal notional, maximum 10% per position, whole shares, cash retained | Confirmed | — |
| DEC-2026-015 | Partitions | Train 2011–18, validation 2019–21, dev test 2022–23, final OOS 2024–25 | Pending data verification | — |
| DEC-2026-016 | Walk-forward | Anchored annual refits through 2023; rolling window is robustness only | Confirmed | — |
| DEC-2026-017 | OOS protection | Separate sealed manifest; one frozen-release evaluation in Phase 8 | Pending technical implementation | — |
| DEC-2026-018 | Purge/embargo | 20 sessions, adjusted upward if label horizon grows | Confirmed | — |
| DEC-2026-019 | Baseline acceptance | Deterministic and audited reference; candidate requires positive net excess on validation/dev test | Confirmed | — |
| DEC-2026-020 | ML adoption | Pre-committed multi-fold, net Sharpe, dev-test, MDD, and 2× cost gates | Confirmed | — |
| DEC-2026-021 | Experiment recording | Registry row pre-result; immutable hashes/results | Confirmed | — |
| DEC-2026-022 | Paper entry | Phase 8 approval, frozen release, 60 sessions and 30 completed exits plus cases | Pending broker selection | — |
| DEC-2026-023 | Live entry | OOS/robustness/paper gates, 90 sessions, 50 exits, explicit capital approval | Confirmed | — |
| DEC-2026-024 | Kill switches | Hard operational stops plus 3% daily / 12% drawdown risk stop | Pending execution implementation | — |

## Phase-1 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-025 | Authoritative data family | KRX official historical extract/Data Marketplace is primary; third-party libraries may only bootstrap or cross-check | Pending acquisition | — |
| DEC-2026-026 | Missing-source treatment | Missing historical constituents, events, or bars block the build; no current-universe or interpolated-price substitution | Confirmed | — |
| DEC-2026-027 | Final-OOS storage | Development through 2023 and sealed 2024–2025 outputs use separate directories and manifests | Implemented and synthetically tested | DEC-2026-017 implementation |
| DEC-2026-028 | Temporary storage format | Deterministic gzip CSV is permitted for validation in the dependency-limited runtime; Phase 1 gate still requires Parquet or DuckDB conversion | Temporary, gate not satisfied | — |
| DEC-2026-029 | Phase-1 status | Code and schema are ready; actual-data validation is blocked until an auditable KRX bundle is supplied or reachable | Blocked | — |
| DEC-2026-030 | Supplied-export normalization | Preserve original hashes; normalize the two user-supplied files with a deterministic adapter; do not infer missing source metadata | Implemented, provenance pending | — |
| DEC-2026-031 | Provisional calendar | Derive session dates from index observations for data alignment; leave official hours and early-close flags unknown | Implemented with warnings | — |
| DEC-2026-032 | 99-member sessions | Preserve all supplied 99-member sessions and fail the frozen exactly-100 gate; never invent or nearest-date-fill a constituent | Pending authoritative resolution | DEC-2026-026 application |
| DEC-2026-033 | Phase-1 partial-data status | Membership and index inputs are normalized, but the build remains blocked by missing stock OHLCV/actions/suspensions, provisional identity, and unresolved lineage | Blocked | DEC-2026-029 |

## Phase-1 Finalization and Phase-2 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-034 | Phase-1 v24 final status | Production v24 independently audited: daily PIT data, 174 securities, 98 corporate actions, 318 intraday files, and sealed 2024–2025 partition | Completed | DEC-2026-029, DEC-2026-033 |
| DEC-2026-035 | Phase-2 engine boundary | Engine consumes pre-frozen orders and never creates features, ranks, signals, labels, or models | Confirmed | — |
| DEC-2026-036 | Deterministic execution order | Corporate actions before open; sells before buys; then priority, security ID, and order ID | Confirmed | — |
| DEC-2026-037 | Accounting precision | Decimal arithmetic; whole shares; statutory charges and proxy commissions rounded down to one KRW | Confirmed for research | DEC-2026-012 implementation |
| DEC-2026-038 | Unresolved corporate actions | Abort a run if a held position reaches an event without complete portfolio terms; never guess entitlements | Confirmed | — |
| DEC-2026-039 | Phase-2 status | 26/26 project tests, 17/17 Phase-2 tests, and 250/250 seeded accounting stress scenarios pass; deterministic artifacts and 7/7 reconciliation checks pass | Completed | — |

## Phase-3 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-040 | Reference signal | Close above SMA200 and 126-session stock return above KOSPI100 return; rank descending by 126-session excess return; no rank-loss exit | Confirmed | — |
| DEC-2026-041 | Validation-only baseline selection | Among only `H={5,10,20}` and `N={5,10,15}`, select highest net Sharpe with frozen tie-breaks; selected `H=20, N=10` | Completed | DEC-2026-008, DEC-2026-013 implementation |
| DEC-2026-042 | Phase-3 status | Accept the deterministic/cost-aware reference; reject it as a trading candidate because Validation (−61.82 pp) and Development Test (−1.12 pp) net excess returns are negative | Completed | DEC-2026-019 application |
| DEC-2026-043 | Phase-4 boundary | Keep final OOS sealed and stop after Phase 3; do not begin feature research without explicit user approval | Confirmed | — |

## Decision Entry Template

```markdown
### DEC-YYYY-### — Short title

- Date:
- Stage:
- Status: Proposed | Confirmed | Pending verification | Superseded | Rejected
- Decision owner:
- Related experiment IDs:
- Previous/superseded decision:
- Recommendation:
- Reason and evidence:
- Important alternative considered:
- Expected impact:
- Final-OOS impact: None | Invalidates current OOS | Requires a new OOS period
- Approval record:
```
