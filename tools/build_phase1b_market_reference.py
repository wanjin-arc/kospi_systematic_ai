#!/usr/bin/env python3
"""Build an all-KOSPI reference panel without loading post-2023 files."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json
from pathlib import Path
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--max-date',default='2023-12-31');a=p.parse_args(argv)
 if a.max_date > '2023-12-31':
  raise ValueError('Phase 1B does not permit post-2023 raw data.')
 files=[]
 # Enumerate only the explicitly permitted physical year partitions.  Do not
 # scan a parent directory which could contain later, unapproved partitions.
 for year in range(2011, 2024):
  for f in sorted((a.raw_root/'raw'/'market_stk'/str(year)).glob('*.csv.gz')):
   d=f.stem.split('.')[0]
   if len(d) != 8 or not d.isdigit():
    raise ValueError(f'invalid market partition filename: {f.name}')
   day=f'{d[:4]}-{d[4:6]}-{d[6:8]}'
   if day <= a.max_date:
    files.append((day,f))
 if not files: raise FileNotFoundError('no permitted market partitions')
 a.output_root.mkdir(parents=True,exist_ok=True);out=a.output_root/'all_kospi_market_reference.csv';prev={};rows=[]
 for day,f in files:
  rets=[]; values=[];count=0
  with gzip.open(f,'rt',encoding='cp949',errors='replace',newline='') as h:
   for i,r in enumerate(csv.reader(h)):
    if i==0 or len(r)<10 or not r[0].strip().isdigit():continue
    try: close=float(r[2].replace(',',''));value=float(r[9].replace(',',''))
    except ValueError:continue
    t=r[0].strip().zfill(6); old=prev.get(t);prev[t]=close;count+=1;values.append(value)
    if old and old>0:rets.append(close/old-1)
  rets.sort();n=len(rets);median=rets[n//2] if n else '';advance=sum(x>0 for x in rets)/n if n else ''
  stdev=(sum((x-sum(rets)/n)**2 for x in rets)/n)**.5 if n else ''
  rows.append({'date':day,'all_kospi_observed_count':count,'all_kospi_total_trading_value':format(sum(values),'.12g'),'all_kospi_advance_ratio':format(advance,'.12g') if n else '','all_kospi_median_return_1d':format(median,'.12g') if n else '','all_kospi_return_dispersion_1d':format(stdev,'.12g') if n else ''})
 with out.open('w',encoding='utf-8',newline='') as h:
  w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 manifest={'schema_version':'phase1b-market-reference-v1','role':'reference_only_not_universe','max_loaded_date':max(r['date'] for r in rows),'post_2023_files_loaded':False,'rows':len(rows),'source_root':str(a.raw_root),'source_root_manifest_sha256':sha(a.raw_root/'manifest.json'),'output_sha256':sha(out)}
 (a.output_root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(manifest,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
