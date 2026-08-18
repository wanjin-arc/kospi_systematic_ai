# Phase 1 Source Audit

**Audit date:** 2026-08-16  
**Conclusion:** Historical membership and index-price files are available and internally consistent, but their upstream lineage is not yet auditable and four required data domains remain unresolved.

## Received files

| File | SHA-256 | Embedded metadata assessment |
|---|---|---|
| `kospi100_membership_daily(2).csv` | `4a9adec2dc0c208a8329d73c015bf234cb5c939dac1f1a65490ec3da1c22da48` | Daily date/ticker/name/member flag only; no source screen, query, retrieval time, announcement time, ISIN, or licence |
| `개별지수시세추이 (20100104~20251230)(2).csv` | `369cb7bfb07839432dba33f3935f437d2c2bda8eafd1a098a3bca71100e3e9be` | KRX-style CP949 field layout; no index code/name, query parameters, retrieval time, URL, or licence embedded |

The project context identifies the second file as KOSPI 100, but that identity is not independently encoded in the file. The normalized `KOSPI100` code is therefore a project identifier, not evidence of an official source code.

## Normalization decisions

- Original files are unchanged; normalized rows retain original filename and hash.
- Daily membership snapshots are compressed into inclusive-start/exclusive-end intervals only after verifying a complete weekday grid.
- Six-digit display codes receive provisional IDs of the form `KRX_CODE:000000`. This does not resolve code reuse or code changes.
- Index observations define the provisional exchange-session date list. Official market hours and early-close flags remain blank.
- Eight descending two-year index blocks are sorted ascending.
- Six concatenation-boundary `일자` strings attached to the unused market-cap field are removed after explicit detection; no OHLCV field is altered by that repair.
- Index volume and traded-value units are converted to shares and KRW.

## Authoritative source requirement

The preferred authoritative family remains the [KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd) or a KRX historical/custom extract with reproducible query evidence. The [KRX Open API](https://openapi.krx.co.kr/) is suitable only if its product coverage, retention, authentication, and permitted use are verified. KRX's [market-data usage policy](https://data.krx.co.kr/inc/datasale/Market%20Data%20Usage%20Polices_ko.pdf?v=20250732) must be reviewed before non-display algorithmic production use.

For each supplied file, retain or provide:

- source organisation and product/screen name;
- index code and selected parameters;
- requested date range and export procedure;
- retrieval timestamp in KST;
- source URL or request reference;
- licence/terms reference;
- a screenshot, request log, or original per-query export when files were manually combined.

## Remaining acquisition bundle

1. Raw daily OHLCV and traded value for all point-in-time members, including 2010 warm-up history.
2. Split, reverse-split, stock-dividend, code-change, listing, and delisting events.
3. Trading-suspension intervals and documented market status.
4. ISIN or another evidence-backed stable identity map.
5. Official trading-session hours and early-close indicators.
6. Authoritative evidence for the 26 sessions with 99 supplied constituents.

## Cross-check policy

An independent wrapper/vendor copy may identify discrepancies but cannot silently overwrite the supplied or official raw data. Disagreements remain recorded until resolved against an authoritative source. Current-constituent backfill, interpolated prices, and invented constituents are prohibited.
