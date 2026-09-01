#!/usr/bin/env python3
"""Fetch missing DART document ZIPs for unresolved v25 action receipts.

The key is requested interactively and never stored or printed. Existing files
are reused; the output is a separate incoming directory and is not merged
automatically. Use --max-requests to respect the daily API quota.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, time, urllib.parse, urllib.request, zipfile, io
from getpass import getpass
from pathlib import Path

BASE="https://opendart.fss.or.kr/api/document.xml"
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--candidate-csv",type=Path,required=True); p.add_argument("--output-root",type=Path,required=True); p.add_argument("--max-requests",type=int,default=100); p.add_argument("--delay",type=float,default=0.25); a=p.parse_args(argv)
    a.output_root.mkdir(parents=True,exist_ok=True); (a.output_root/"documents").mkdir(exist_ok=True)
    receipts=[]
    with a.candidate_csv.open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            receipt=r.get("canonical_event_id","").removeprefix("DART:")
            if receipt and not (a.output_root/"documents"/f"{receipt}.zip").exists(): receipts.append(receipt)
    receipts=sorted(set(receipts)); key=getpass("OpenDART API key (input is not stored or printed): ").strip() if receipts else ""
    if receipts and not key: raise SystemExit("API key is required")
    rows=[]
    planned = receipts if a.max_requests <= 0 else receipts[:a.max_requests]
    for i,receipt in enumerate(planned,1):
        query=urllib.parse.urlencode({"crtfc_key":key,"rcept_no":receipt}); status="ERROR"; detail=""
        try:
            with urllib.request.urlopen(f"{BASE}?{query}",timeout=45) as response: raw=response.read()
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z: z.testzip()
                path=a.output_root/"documents"/f"{receipt}.zip"; path.write_bytes(raw); status="DOWNLOADED"
            except zipfile.BadZipFile:
                detail=raw[:200].decode("utf-8",errors="replace"); status="NON_ZIP_RESPONSE"
        except Exception as exc: detail=str(exc)
        rows.append({"rcept_no":receipt,"status":status,"detail":detail}); time.sleep(max(0,a.delay))
        if i%50==0: print(f"requested={i}/{len(planned)}")
    with (a.output_root/"fetch_audit.csv").open("w",encoding="utf-8",newline="") as f: w=csv.DictWriter(f,fieldnames=["rcept_no","status","detail"]); w.writeheader(); w.writerows(rows)
    manifest={"schema_version":"v25-dart-document-fetch-v1","planned_missing":len(receipts),"requested":len(rows),"downloaded":sum(r["status"]=="DOWNLOADED" for r in rows),"output_root":str(a.output_root),"api_key_stored":False}
    (a.output_root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(manifest,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
