import argparse,json,re,time,urllib.request,urllib.error
from transformers import AutoTokenizer
p=argparse.ArgumentParser(); p.add_argument('--api',required=True); p.add_argument('--model-path',required=True); p.add_argument('--tokens',type=int,nargs='+',required=True); p.add_argument('--out',required=True); a=p.parse_args()
tok=AutoTokenizer.from_pretrained(a.model_path,trust_remote_code=True)
fid=tok.encode(' alpha',add_special_tokens=False); assert len(fid)==1; fid=fid[0]
def build(target):
    codes=[f'K{i+1}-{target}-ZX{(target//1000+i*37)%997:03d}' for i in range(5)]
    needles=[tok.encode(f'\nIMPORTANT FACT {i+1}: validation code = {c}.\n',add_special_tokens=False) for i,c in enumerate(codes)]
    q=tok.encode('\nReturn exactly the five validation codes in order, separated only by commas.\n',add_special_tokens=False)
    nfill=target-sum(map(len,needles))-len(q); assert nfill>1000
    weights=[.10,.20,.20,.20,.20]; seg=[int(nfill*w) for w in weights]; seg.append(nfill-sum(seg))
    ids=[]
    for i,n in enumerate(needles): ids += [fid]*seg[i]+n
    ids += [fid]*seg[-1]+q
    text=tok.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False)
    return text,codes,len(tok.encode(text,add_special_tokens=False))
def run(target):
    text,codes,content_tokens=build(target)
    body={'model':'qwen3.8-27b','messages':[{'role':'user','content':text}],'temperature':0,'seed':4242,'max_tokens':64,'chat_template_kwargs':{'enable_thinking':False},'stream':True,'stream_options':{'include_usage':True}}
    req=urllib.request.Request(a.api+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    t0=time.monotonic(); first=None; chunks=[]; usage={}; err=None
    try:
        with urllib.request.urlopen(req,timeout=1800) as r:
            for raw in r:
                s=raw.decode(errors='replace').strip()
                if not s.startswith('data: '): continue
                ev=s[6:]
                if ev=='[DONE]': break
                x=json.loads(ev); usage=x.get('usage') or usage
                for ch in x.get('choices') or []:
                    d=ch.get('delta') or {}; z=(d.get('content') or '')+(d.get('reasoning_content') or '')
                    if z: first=first or time.monotonic(); chunks.append(z)
    except Exception as e: err=f'{type(e).__name__}: {e}'
    end=time.monotonic(); out=''.join(chunks).strip(); pos=[]; start=0
    for c in codes:
        j=out.find(c,start); pos.append(j); start=j+len(c) if j>=0 else start
    ordered=all(x>=0 for x in pos) and pos==sorted(pos)
    norm=re.sub(r'\s+','',out).strip('`[]"\' '); expected=','.join(codes)
    return {'target_content_tokens':target,'content_tokens':content_tokens,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'codes':codes,'output':out,'ordered_all_found':ordered,'exact_format':norm==expected,'ttft_s':None if first is None else first-t0,'total_s':end-t0,'error':err}
res=[run(x) for x in a.tokens]
json.dump({'results':res,'all_accuracy_pass':all(r['ordered_all_found'] and not r['error'] for r in res)},open(a.out,'w'),ensure_ascii=False,indent=2)
print(json.dumps({'all_accuracy_pass':all(r['ordered_all_found'] and not r['error'] for r in res),'rows':[{'target':r['target_content_tokens'],'prompt':r['prompt_tokens'],'pass':r['ordered_all_found'],'exact':r['exact_format'],'ttft':r['ttft_s'],'total':r['total_s']} for r in res]},ensure_ascii=False))