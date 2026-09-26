"""opt_ab.py — optimization A/B for a top candidate: KV cache type, Flash Attention,
speculative decoding (embedded MTP / DFlash2 sidecar / ngram). Correctness probes at 128K.
Usage: uv run python opt_ab.py <image> <gpu> <model_path> <model_key> [ctx] [port]
Output: evidence runs/opt/<model_key>.json
"""
from __future__ import annotations
import json, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

DFLASH = "/prodmodels/Qwen3.8-27B-DFlash2-Q4_K_M.gguf"

CONFIGS = [
    {"id": "kv-f16_fa-on", "kv": "f16 f16", "fa": "on", "spec": "", "ctx": 131072},
    {"id": "kv-q8_fa-on", "kv": "q8_0 q8_0", "fa": "on", "spec": "", "ctx": 262144},
    {"id": "kv-q4_fa-on", "kv": "q4_0 q4_0", "fa": "on", "spec": "", "ctx": 262144},
    {"id": "kv-q4_fa-off", "kv": "q4_0 q4_0", "fa": "off", "spec": "", "ctx": 131072},
    {"id": "kv-q4_mtp", "kv": "q4_0 q4_0", "fa": "on", "spec": "--spec-type draft-mtp", "ctx": 262144},
    {"id": "kv-q4_dflash", "kv": "q4_0 q4_0", "fa": "on", "spec": f"--spec-type draft-dflash -md {DFLASH} --spec-draft-n-max 7 --spec-draft-type-k q8_0 --spec-draft-type-v q8_0", "ctx": 262144},
    {"id": "kv-q4_ngram", "kv": "q4_0 q4_0", "fa": "on", "spec": "--spec-type ngram-cache", "ctx": 262144},
]


def correctness(port: int, filler: str) -> dict:
    out = {}
    # needle at 128K-ish
    sub, n = lab.cut_to_tokens(filler, port, 131072 - 2048)
    doc = sub[: len(sub) // 2] + "\n【内部备忘】评审密码 X7K9-42ZQ。\n" + sub[len(sub) // 2:]
    r = lab.chat(port, [{"role": "user", "content": doc + "\n\n会议密码是什么？只输出密码。"}],
                 max_tokens=600, temperature=0.0, seed=42)
    out["needle128k"] = 1 if "X7K9-42ZQ" in r["text"] else 0
    out["needle128k_wall"] = r["wall_s"]
    # strict json
    r2 = lab.chat(port, [{"role": "user", "content": '只输出 JSON：{"ok":true,"n":7}'}], max_tokens=120,
                  temperature=0.0, seed=1, extra={"response_format": {"type": "json_object"}})
    try:
        j = json.loads(r2["text"].strip().strip("`"))
        out["json_ok"] = 1 if j.get("n") == 7 else 0
    except Exception:
        out["json_ok"] = 0
    # coding-lite (roman)
    import re, subprocess
    r3 = lab.chat(port, [{"role": "user", "content": "写 python 函数 romanToInt(s)->int。只输出 ```python 块。"}],
                  max_tokens=1200, temperature=0.0, seed=42)
    m = re.search(r"```python\n(.*?)```", r3["text"], re.S)
    out["coding_lite"] = 0
    if m:
        p = subprocess.run([sys.executable, "-I", "-c", m.group(1) + "\nassert romanToInt('MCMXCIV')==1994\nassert romanToInt('III')==3\nprint('OK')"],
                           capture_output=True, text=True, timeout=60)
        out["coding_lite"] = 1 if p.returncode == 0 else 0
    return out


def ladder(port: int, cname: str, filler: str, steps=(32768, 131072, 262144)) -> list:
    res = []
    for target in [s for s in steps if s <= max(steps)]:
        sub, n = lab.cut_to_tokens(filler, port, target - 4096)
        if n < target // 2:
            continue
        lab._LASTLOG_POS[cname] = len(lab.docker_logs(cname))
        r = lab.chat(port, [{"role": "user", "content": sub + "\n\n一句话总结。"}], max_tokens=160, temperature=0.0, seed=42)
        tps = lab.parse_tps(cname)
        res.append({"ctx": target, "n": n, "ttft_s": r["ttft_s"], "wall_s": r["wall_s"],
                    "ptps": tps["prompt_tps"][-1] if tps["prompt_tps"] else None,
                    "dtps": tps["decode_tps"][-1] if tps["decode_tps"] else None})
    return res


def main():
    image, gpu, model_path, key = sys.argv[1:5]
    ctx = int(sys.argv[5]) if len(sys.argv) > 5 else 262144
    port = int(sys.argv[6]) if len(sys.argv) > 6 else 18201
    out = {"model": key, "path": model_path, "ctx": ctx, "configs": []}
    for i, cfg in enumerate(CONFIGS):
        cname = f"opt-{key}-{cfg['id']}"
        ctx = cfg.get("ctx", ctx)
        kvk, kvv = cfg["kv"].split()
        cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c {ctx} -np 1 -ngl 999 "
               f"--cache-type-k {kvk} --cache-type-v {kvv} -fa {cfg['fa']} --jinja -a opt "
               f"-b 1024 -ub 1024 --metrics {cfg['spec']}")
        rec = {"id": cfg["id"], "ctx": ctx}
        try:
            lab._LASTLOG_POS.pop(cname, None)
            rec["health_s"] = round(lab.server_up(cname, image, port, gpu, cmd), 1)
            rec["vram_after_load"] = lab.vram_mib(gpu)
            filler, _ = lab.make_filler(ctx, port)
            rec["correctness"] = correctness(port, filler)
            rec["ladder"] = ladder(port, cname, filler, steps=tuple(s for s in (32768, 131072, 262144) if s <= ctx))
            rec["vram_peak"] = lab.vram_mib(gpu)
            logs = lab.docker_logs(cname)
            import re as _re
            acc = _re.findall(r"accepting up to \d+ tokens?|accepted.*per step", logs)
            rec["spec_lines"] = acc[:3]
        except Exception as e:
            rec["error"] = str(e)[:300]
            rec["logs_tail"] = lab.docker_logs(cname)[-3000:] if lab.sh(["docker", "ps", "-a", "--filter", f"name={cname}", "--format", "{{.Names}}"]).stdout.strip() else "(gone)"
        finally:
            lab.server_down(cname)
        out["configs"].append(rec)
        print(f"== cfg {cfg['id']}: {json.dumps({k: rec.get(k) for k in ('health_s','error')}, ensure_ascii=False)} corr={rec.get('correctness')}", flush=True)
    lab.write_json(lab.EVID / "runs" / "opt" / f"{key}.json", out)
    print("OPT DONE")


if __name__ == "__main__":
    main()
