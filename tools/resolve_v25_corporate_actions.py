#!/usr/bin/env python3
"""Resolve only mechanically testable v25 corporate-action evidence.

The tool joins DART structured terms with KRX listed-share observations around
the proposed effective date.  It never writes the Phase-1 adjustment table;
rows lacking a date, ratio, or PIT identity remain blocked.
"""
from __future__ import annotations
import argparse, csv, gzip, json, re, hashlib, zipfile
from datetime import date, timedelta
from pathlib import Path

ACTION_TYPES = {"BONUS_ISSUE", "CAPITAL_REDUCTION", "STOCK_SPLIT_OR_REVERSE_SPLIT", "MERGER", "COMPANY_SPLIT", "COMPANY_SPLIT_MERGER", "SHARE_EXCHANGE_TRANSFER"}
def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()
def digits(value: object) -> str:
    return "".join(re.findall(r"\d", str(value)))
def date8(value: object) -> str:
    d=digits(value)
    for i in range(max(0,len(d)-7)):
        part=d[i:i+8]
        if part[:4].startswith("20") and 1 <= int(part[4:6]) <= 12 and 1 <= int(part[6:]) <= 31: return part
    return ""
def date_fragment(value: str) -> str:
    m=re.search(r"(20\d{2})[^0-9]{0,20}(\d{1,2})[^0-9]{0,20}(\d{1,2})",value)
    if not m: return date8(value)
    y,mo,day=map(int,m.groups())
    try:
        date(y,mo,day)
    except ValueError:
        return ""
    return f"{y:04d}{mo:02d}{day:02d}"
def walk(obj):
    if isinstance(obj, dict):
        for k,v in obj.items(): yield str(k),v; yield from walk(v)
    elif isinstance(obj, list):
        for v in obj: yield from walk(v)
def first_date(payload: dict) -> str:
    keys=("cr_std","effd","effective_date","crsc_nstkdlprd","bddd")
    flat=list(walk(payload))
    for key in keys:
        for k,v in flat:
            if k == key and date8(v): return date8(v)
    return ""
def first_ratio(payload: dict) -> float | None:
    for k,v in walk(payload):
        if k in {"cr_rt_ostk","cr_rt_estk","cr_rt","ratio","share_multiplier"}:
            s=str(v).replace(",","").replace("%","").strip()
            try:
                x=float(s)
                if x > 0: return x/100 if x > 1 else x
            except ValueError: pass
    return None
def document_terms(root: Path, receipt: str, extra_root: Path | None = None) -> tuple[str, float | None, str]:
    archive=root/"documents"/f"{receipt}.zip"
    if not archive.exists() and extra_root is not None:
        archive=extra_root/"documents"/f"{receipt}.zip"
    if not archive.exists(): return "", None, "DOCUMENT_NOT_ARCHIVED"
    try:
        with zipfile.ZipFile(archive) as z:
            names=[n for n in z.namelist() if n.lower().endswith((".xml",".txt"))]
            if not names: return "", None, "DOCUMENT_NO_TEXT"
            raw=z.read(names[0]); text=raw.decode("cp949",errors="replace")
    except (OSError,zipfile.BadZipFile): return "", None, "DOCUMENT_READ_ERROR"
    compact=re.sub(r"<[^>]+>", " ", text)
    compact=compact.replace("&cr;"," ")
    date_value=""
    for label in ("합병기일","분할기일","감자기준일","효력발생일","주식분할기준일","권리락일"):
        m=re.search(label+r".{0,180}?((?:20\d{2})[^0-9]{0,20}(?:0?[1-9]|1[0-2])[^0-9]{0,20}(?:0?[1-9]|[12]\d|3[01]))",compact,re.S)
        if m:
            date_value=date_fragment(m.group(1));
            if date_value: break
    ratio=None
    m=re.search(r"(?:합병비율|감자비율|주식분할|액면분할).{0,100}?([0-9]+(?:\.[0-9]+)?)\s*[:：/]\s*([0-9]+(?:\.[0-9]+)?)",compact,re.S)
    if m:
        try: ratio=float(m.group(2))/float(m.group(1))
        except ZeroDivisionError: ratio=None
    return date_value,ratio,"DOCUMENT_XML_TERMS"
def load_prices(root: Path, tickers: set[str]) -> dict[tuple[str,str], int]:
    out={}
    for p in sorted((root/"raw"/"market_stk").glob("*/*.csv.gz")):
        day=p.stem.split(".")[0]; iso=f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        with gzip.open(p,"rt",encoding="cp949",errors="replace",newline="") as f:
            for n,row in enumerate(csv.reader(f)):
                if n==0 or len(row)<12: continue
                t=row[0].strip().zfill(6)
                if t in tickers:
                    try: out[(iso,t)]=int(row[11].replace(",",""))
                    except ValueError: pass
    return out
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--triage-csv",type=Path,required=True); p.add_argument("--dart-root",type=Path,required=True); p.add_argument("--extra-documents-root",type=Path); p.add_argument("--krx-root",type=Path,required=True); p.add_argument("--membership",type=Path,required=True); p.add_argument("--output-root",type=Path,required=True); a=p.parse_args(argv)
    members=set(); member_dates={}
    with a.membership.open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            if r.get("is_member","").lower() in {"true","1","yes"}: members.add(r["ticker"].zfill(6)); member_dates.setdefault(r["date"],set()).add(r["ticker"].zfill(6))
    candidates=[]
    with a.triage_csv.open(encoding="utf-8-sig",newline="") as f:
        candidates=[r for r in csv.DictReader(f) if r["ticker"].zfill(6) in members and r["event_type_candidate"] in ACTION_TYPES]
    prices=load_prices(a.krx_root,{r["ticker"].zfill(6) for r in candidates}); out=[]
    for r in candidates:
        ticker=r["ticker"].zfill(6); year=r["rcept_dt"][:4]; payload=None
        for label in ("capital_reduction","company_split","company_split_merger"):
            f=a.dart_root/"structured"/label/r["corp_code"]/f"{year}.json"
            if f.exists():
                try:
                    q=json.loads(f.read_text(encoding="utf-8"))
                    if q.get("status")=="000": payload=q; break
                except (OSError,json.JSONDecodeError): pass
        eff=first_date(payload) if payload else ""; ratio=first_ratio(payload) if payload else None; evidence="STRUCTURED_JSON" if payload else ""
        if not eff or (ratio is None and r["event_type_candidate"] in {"BONUS_ISSUE","CAPITAL_REDUCTION","STOCK_SPLIT_OR_REVERSE_SPLIT"}):
            doc_eff,doc_ratio,doc_status=document_terms(a.dart_root,r["rcept_no"],a.extra_documents_root)
            if doc_eff: eff=doc_eff
            if doc_ratio is not None: ratio=doc_ratio
            if doc_status.startswith("DOCUMENT_"): evidence=doc_status
        status="BLOCKED_NO_DOCUMENT_TERMS" if not eff else ("TERMS_EXTRACTED_PIT_IDENTITY_PENDING" if ratio is None else "TERMS_EXTRACTED_PIT_IDENTITY_PENDING")
        out.append({"canonical_event_id":f"DART:{r['rcept_no']}","ticker":ticker,"filing_date":r["rcept_dt"],"event_type":r["event_type_candidate"],"effective_date":eff,"share_ratio":("" if ratio is None else f"{ratio:.12g}"),"member_on_effective_date":str(bool(eff and ticker in member_dates.get(f'{eff[:4]}-{eff[4:6]}-{eff[6:]}',set()))),"evidence":evidence,"status":status})
    a.output_root.mkdir(parents=True,exist_ok=True); outp=a.output_root/"corporate_actions_v25_resolution_candidates.csv"
    fields=list(out[0]) if out else ["canonical_event_id","ticker","filing_date","event_type","effective_date","share_ratio","member_on_effective_date","evidence","status"]
    with outp.open("w",encoding="utf-8",newline="") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(sorted(out,key=lambda x:(x["filing_date"],x["ticker"])))
    manifest={"schema_version":"v25-corporate-action-resolution-candidates-v1","rows":len(out),"in_universe_mechanical_candidates":len(candidates),"status_counts":{s:sum(x["status"]==s for x in out) for s in sorted({x["status"] for x in out})},"automatic_adjustments_emitted":0,"model_release":False,"output_sha256":sha256(outp)}
    (a.output_root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(manifest,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
