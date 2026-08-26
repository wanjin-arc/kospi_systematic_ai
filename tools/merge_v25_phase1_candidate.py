#!/usr/bin/env python3
"""Merge a released v25 Phase-1 candidate into a new dataset only.

The command deliberately refuses the current blocked candidate.  It is a
reproducible merge gate, not a way to bypass unresolved corporate actions.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

TABLES=("ohlcv_raw.csv","index_ohlcv_raw.csv","universe_membership.csv","symbol_master.csv","trading_calendar.csv","corporate_actions.csv","suspensions.csv")
def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--existing-root",type=Path,required=True); p.add_argument("--candidate-root",type=Path,required=True); p.add_argument("--output-root",type=Path,required=True); a=p.parse_args(argv)
    manifest=json.loads((a.candidate_root/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status")!="RELEASED" or not manifest.get("allow_model_use"):
        raise SystemExit("v25 candidate is blocked; corporate-action and identity terms must be resolved before merge")
    a.output_root.mkdir(parents=True,exist_ok=True); counts={}
    for table in TABLES:
        left=a.existing_root/table; right=a.candidate_root/table; out=a.output_root/table
        if not left.exists() or not right.exists(): raise FileNotFoundError(f"missing table: {table}")
        with left.open(encoding="utf-8-sig",newline="") as f: ld=csv.DictReader(f); l=list(ld); lf=ld.fieldnames or []
        with right.open(encoding="utf-8-sig",newline="") as f: rd=csv.DictReader(f); r=list(rd); rf=rd.fieldnames or []
        if not l and not r: out.write_text("\n",encoding="utf-8"); counts[table]=0; continue
        keys=list(lf or rf)
        if lf != rf: raise ValueError(f"schema mismatch: {table}")
        merged={tuple(row.get(k,"") for k in keys):row for row in l}
        for row in r:
            if set(row)!=set(keys): raise ValueError(f"schema mismatch: {table}")
            merged.setdefault(tuple(row[k] for k in keys),row)
        with out.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(sorted(merged.values(),key=lambda x:tuple(x.values())))
        counts[table]=len(merged)
    payload={"schema_version":"v25-phase1-merged-v1","status":"RELEASED","allow_model_use":True,"existing_root":str(a.existing_root),"candidate_manifest_sha256":sha256(a.candidate_root/"manifest.json"),"counts":counts}
    (a.output_root/"manifest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
