#!/usr/bin/env python3
import argparse, csv, json, re, statistics
from pathlib import Path

PAT = re.compile(r"vllm(027|028)-c(\d+)-(\d+)\.json$")

def load_rows(paths, source):
    rows=[]
    for p in sorted(paths):
        m=PAT.match(p.name)
        if not m: continue
        d=json.loads(p.read_text())
        req=d.get('rows') or []
        tt=[r.get('ttft_s') for r in req if r.get('ttft_s') is not None]
        total=[r.get('total_s') for r in req if r.get('total_s') is not None]
        prompts=[r.get('prompt_tokens') for r in req if r.get('prompt_tokens')]
        rows.append({
            'source':source,'version':m.group(1),'concurrency':int(m.group(2)),
            'target_tokens':int(m.group(3)),'status':d.get('status'),
            'usable':bool(d.get('usable')),'full_resident':bool(d.get('full_resident_concurrency')),
            'max_running':d.get('max_running'),'max_waiting':d.get('max_waiting'),
            'max_waiting_capacity':d.get('max_waiting_capacity'),'max_kv_usage':d.get('max_kv_usage'),
            'preemptions_delta':d.get('preemptions_delta'),'server_alive_after':d.get('server_alive_after'),
            'wall_s':d.get('wall_s'),'prompt_tokens_min':min(prompts) if prompts else None,
            'prompt_tokens_max':max(prompts) if prompts else None,
            'ttft_median_s':statistics.median(tt) if tt else None,
            'request_total_median_s':statistics.median(total) if total else None,
            'file':p.name,
        })
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--usable-dir',required=True); ap.add_argument('--resident-dir')
    ap.add_argument('--out-dir',required=True); a=ap.parse_args()
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    rows=load_rows(Path(a.usable_dir).glob('*.json'),'usable')
    if a.resident_dir and Path(a.resident_dir).exists():
        rows += load_rows(Path(a.resident_dir).glob('*.json'),'resident')
    cols=list(rows[0]) if rows else []
    with (out/'matrix.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    safe={}; resident={}
    for r in rows:
        key=f"vllm{r['version']}-c{r['concurrency']}"
        if r['source']=='usable' and r['usable']:
            safe[key]=max(safe.get(key,0),r['target_tokens'])
        if r['usable'] and r['full_resident']:
            resident[key]=max(resident.get(key,0),r['target_tokens'])
    comparisons=[]
    idx={(r['source'],r['version'],r['concurrency'],r['target_tokens']):r for r in rows}
    for r in rows:
        if r['version']!='027': continue
        b=idx.get((r['source'],'028',r['concurrency'],r['target_tokens']))
        if not b: continue
        def pct(x,y): return None if not x or y is None else (y/x-1)*100
        comparisons.append({'source':r['source'],'concurrency':r['concurrency'],'target_tokens':r['target_tokens'],
            '027_status':r['status'],'028_status':b['status'],
            'wall_027_s':r['wall_s'],'wall_028_s':b['wall_s'],'wall_delta_028_pct':pct(r['wall_s'],b['wall_s']),
            'ttft_median_027_s':r['ttft_median_s'],'ttft_median_028_s':b['ttft_median_s'],
            'ttft_delta_028_pct':pct(r['ttft_median_s'],b['ttft_median_s']),
            'max_running_027':r['max_running'],'max_running_028':b['max_running'],
            'max_kv_027':r['max_kv_usage'],'max_kv_028':b['max_kv_usage']})
    summary={'safe_admitted_max_tokens':safe,'full_resident_max_tested_tokens':resident,
             'comparisons':comparisons,'rows':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    with (out/'comparison.csv').open('w',newline='') as f:
        ccols=list(comparisons[0]) if comparisons else []
        w=csv.DictWriter(f,fieldnames=ccols); w.writeheader(); w.writerows(comparisons)
    print(json.dumps({'safe':safe,'resident':resident,'row_count':len(rows)},indent=2,sort_keys=True))

if __name__=='__main__': main()
