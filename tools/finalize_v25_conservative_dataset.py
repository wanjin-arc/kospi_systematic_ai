#!/usr/bin/env python3
"""Finalize a conservative dataset without duplicating overlapping v24 rows."""
from __future__ import annotations
import argparse, csv, hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path
def sha256(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--existing-root',type=Path,required=True); p.add_argument('--v25-membership',type=Path,required=True); p.add_argument('--v25-action-manifest',type=Path,required=True); p.add_argument('--output-root',type=Path,required=True); a=p.parse_args(argv)
 a.output_root.mkdir(parents=True,exist_ok=True)
 for src in a.existing_root.iterdir():
  dst=a.output_root/src.name
  if src.is_file(): shutil.copy2(src,dst)
  elif src.is_dir(): shutil.copytree(src,dst,dirs_exist_ok=True)
 existing_dates=set()
 membership_dates=set()
 with (a.existing_root/'membership_daily.csv.gz').open('rb') as _:
  import gzip
  with gzip.open(a.existing_root/'membership_daily.csv.gz','rt',encoding='utf-8',newline='') as f:
   existing_dates={r['date'] for r in csv.DictReader(f)}
 with a.v25_membership.open(encoding='utf-8-sig',newline='') as f: membership_dates={r['date'] for r in csv.DictReader(f)}
 new_dates=sorted(membership_dates-existing_dates)
 action=json.loads(a.v25_action_manifest.read_text(encoding='utf-8'))
 manifest={'schema_version':'v25-conservative-final-dataset-v1','status':'RELEASED_INHERITED_V24_BLOCKED_V25_INCREMENT','model_use':'v24_rows_only','existing_root':str(a.existing_root),'existing_manifest_sha256':sha256(a.existing_root/'partition.json'),'v25_membership_sha256':sha256(a.v25_membership),'v25_action_manifest_sha256':sha256(a.v25_action_manifest),'v25_membership_dates_new':len(new_dates),'v25_membership_new_dates':new_dates,'v25_action_auto_adjustments':action.get('automatic_adjustments_emitted',0),'v25_action_unresolved_rows':action.get('rows',0),'v25_increment_merged_rows':0,'reason':'v25 overlaps existing 2011-2023 data; 2024-2025 lacks PIT membership; unresolved corporate actions are retained as audit only','generated_at_utc':datetime.now(timezone.utc).isoformat()}
 (a.output_root/'manifest_v25_conservative.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print(json.dumps(manifest,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
