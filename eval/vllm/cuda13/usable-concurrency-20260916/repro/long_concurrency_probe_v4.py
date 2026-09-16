#!/usr/bin/env python3
import argparse, concurrent.futures, json, re, threading, time, urllib.request, urllib.error, uuid
from transformers import AutoTokenizer
P=argparse.ArgumentParser(); P.add_argument('--api',required=True); P.add_argument('--concurrency',type=int,required=True); P.add_argument('--tokens',type=int,required=True); P.add_argument('--max-tokens',type=int,default=64); P.add_argument('--out',required=True); a=P.parse_args()
MODEL='qwen3.8-27b'; TOK=AutoTokenizer.from_pretrained('/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128')
WORDS=[' alpha',' omega',' sigma',' delta',' theta',' kappa',' lambda',' gamma']
def exact_prompt(label, word, target):
    base=f'Long concurrency qualification {label}. Read all records before answering.\n'; tail=f'\nEnd marker {label}. Return a concise technical summary.'
    lo,hi=1,target
    while lo<hi:
        n=(lo+hi+1)//2; msg=base+word*n+tail
        k=len(TOK.apply_chat_template([{'role':'user','content':msg}],tokenize=True,add_generation_prompt=True,return_dict=False))
        if k<=target: lo=n
        else: hi=n-1
    msg=base+word*lo+tail; n=len(TOK.apply_chat_template([{'role':'user','content':msg}],tokenize=True,add_generation_prompt=True,return_dict=False))
    return msg,n
def metrics():
    txt=urllib.request.urlopen(a.api+'/metrics',timeout=3).read().decode()
    def one(name,extra=''):
        pat=r'^vllm:'+re.escape(name)+r'\{[^\n]*'+extra+r'[^\n]*\}\s+([0-9.eE+-]+)$'
        m=re.search(pat,txt,re.M); return float(m.group(1)) if m else 0.0
    return {'running':one('num_requests_running'),'waiting':one('num_requests_waiting'),
            'waiting_capacity':one('num_requests_waiting_by_reason','reason="capacity"'),
            'kv':one('kv_cache_usage_perc'),'preempt':one('num_preemptions_total')}
stop=threading.Event(); samples=[]
def sampler():
    while not stop.is_set():
        try: samples.append(metrics())
        except Exception: pass
        stop.wait(0.1)
def run_one(label,content):
    body={'model':MODEL,'messages':[{'role':'user','content':content}],'temperature':0,'seed':4242,
          'max_tokens':a.max_tokens,'ignore_eos':True,'cache_salt':'usable-'+label+'-'+uuid.uuid4().hex,
          'chat_template_kwargs':{'enable_thinking':False},'stream':True,'stream_options':{'include_usage':True}}
    req=urllib.request.Request(a.api+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    started=time.monotonic(); first=last=None; usage={}; err=None; http_status=None; finish=[]; events=[]; content_chars=0; reasoning_chars=0
    try:
        with urllib.request.urlopen(req,timeout=1800) as r:
            http_status=getattr(r,'status',None)
            for raw in r:
                line=raw.decode(errors='replace').strip()
                if not line.startswith('data: '): continue
                ev=line[6:]
                if ev=='[DONE]': break
                try: chunk=json.loads(ev)
                except Exception:
                    if len(events)<8: events.append({'raw':ev[:500]})
                    continue
                if chunk.get('error'):
                    err='stream_error: '+json.dumps(chunk.get('error'),ensure_ascii=False)[:1000]
                usage=chunk.get('usage') or usage; ch=chunk.get('choices') or []
                if len(events)<8: events.append(chunk)
                if ch:
                    c0=ch[0]; delta=c0.get('delta') or {}; fr=c0.get('finish_reason')
                    if fr is not None: finish.append(fr)
                    txt=delta.get('content') or ''; rtxt=delta.get('reasoning_content') or ''
                    content_chars += len(txt); reasoning_chars += len(rtxt)
                    if txt or rtxt:
                        now=time.monotonic(); first=first or now; last=now
    except urllib.error.HTTPError as e:
        http_status=e.code
        try: detail=e.read().decode(errors='replace')[:2000]
        except Exception: detail=''
        err=f'HTTPError {e.code}: {detail}'
    except Exception as e: err=f'{type(e).__name__}: {e}'
    ended=time.monotonic(); comp=int(usage.get('completion_tokens') or 0); prm=int(usage.get('prompt_tokens') or 0)
    reached_limit=(comp==a.max_tokens) or ('length' in finish)
    ok=(err is None and first is not None and (content_chars+reasoning_chars)>0 and reached_limit)
    return {'label':label,'ok':ok,'error':err,'http_status':http_status,'finish_reasons':finish[-4:],
            'content_chars':content_chars,'reasoning_chars':reasoning_chars,'reached_limit':reached_limit,'usage_present':bool(usage),'debug_events':events,
            'prompt_tokens':prm,'completion_tokens':comp,
            'ttft_s':None if first is None else first-started,'total_s':ended-started,
            'decode_s':None if first is None or last is None else last-first,
            'decode_tok_s':None if first is None or last is None else max(comp-1,0)/max(last-first,1e-9)}
prompts=[]
for i in range(a.concurrency):
    p,n=exact_prompt(chr(65+i),WORDS[i%len(WORDS)],a.tokens); prompts.append((chr(65+i),p,n))
before=metrics(); th=threading.Thread(target=sampler,daemon=True); th.start(); wall0=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
    futs=[ex.submit(run_one,l,p) for l,p,_ in prompts]; rows=[f.result() for f in futs]
wall=time.monotonic()-wall0; stop.set(); th.join(timeout=2)
try: after=metrics(); alive=True
except Exception: after={}; alive=False
mr=max([x['running'] for x in samples] or [0]); mw=max([x['waiting'] for x in samples] or [0]); mc=max([x['waiting_capacity'] for x in samples] or [0]); mk=max([x['kv'] for x in samples] or [0])
pre=(after.get('preempt',0)-before.get('preempt',0)) if alive else None
all_ok=all(r['ok'] for r in rows)
resident_peak=(mr>=a.concurrency)
resident_clean=any(x['running']>=a.concurrency and x['waiting']==0 and x['waiting_capacity']==0 for x in samples)
usable=bool(all_ok and alive and pre==0)
res={'status':'PASS' if usable else 'FAIL','usable':usable,'all_requests_ok':all_ok,'server_alive_after':alive,
     'concurrency':a.concurrency,'target_constructed_tokens':a.tokens,'constructed_prompt_tokens':[n for _,_,n in prompts],
     'max_tokens':a.max_tokens,'rows':rows,'wall_s':wall,'max_running':mr,'max_waiting':mw,'max_waiting_capacity':mc,
     'max_kv_usage':mk,'preemptions_delta':pre,'full_resident_concurrency':resident_clean,'full_resident_peak_seen':resident_peak,
     'full_resident_clean_sample_seen':resident_clean,'metrics_before':before,'metrics_after':after}
open(a.out,'w').write(json.dumps(res,indent=2,sort_keys=True)+'\n'); print(json.dumps(res,indent=2,sort_keys=True))
