"""recon_ista.py — ISTA-REASONING-ROOT-CAUSE-RECONCILIATION driver.

Scoped per user instruction: NO big-matrix reruns, NO prod changes.
Set RT_IMAGE env to override runtime image (default b10715).
Usage: uv run python recon_ista.py <model_path> <gpu> <port_base> <out_key>
"""
from __future__ import annotations
import hashlib, json, os, re, subprocess, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab
import httpx

ZH_PROBE = "用中文向新同事解释：什么是 LLM 推理中的 KV cache？为什么量化它能省显存？200 字左右。"
TCP_PROBE = "用一句话说明 TCP 和 UDP 的核心区别。"
CODE_PROBE = "写一个 Python 函数 romanToInt(s: str) -> int，把罗马数字转换为整数。只输出 ```python 代码块。"
QWEN_SAMPLER = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0}

EVID = lab.EVID / "reconciliation"


IMAGE = os.environ.get("RT_IMAGE", "llama-server:cuda12.4-b10715")


def boot(name, gpu, model, port, extra=""):
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    r = subprocess.run(["docker", "run", "-d", "--name", name, "--network", "llama-cpp-model-lab",
                        "--gpus", f'"device={gpu}"', "-p", f"127.0.0.1:{port}:8080",
                        "-v", "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/models:/labmodels:ro",
                        "--restart", "no", IMAGE,
                        "-m", model, "--host", "0.0.0.0", "--port", "8080", "-c", "32768", "-np", "1",
                        "-ngl", "999", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0", "-fa", "on",
                        "--jinja", "-a", name, "--metrics"] + (extra.split() if extra else []),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
    raise RuntimeError(f"{name} not healthy: {logs.stdout[-800:]}{logs.stderr[-800:]}")


def kill(name):
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def apply_template(port, messages, kwargs=None):
    payload = {"messages": messages}
    if kwargs:
        payload["chat_template_kwargs"] = kwargs
    r = httpx.post(f"http://127.0.0.1:{port}/apply-template", json=payload, timeout=60)
    r.raise_for_status()
    j = r.json()
    # b10715 returns {"prompt": "..."} (or similar); keep whole body
    return j


def chat_full(port, messages, max_tokens, sampler, extra=None, reps=3):
    out = []
    for rep in range(reps):
        payload = {"messages": messages, "max_tokens": max_tokens, "stream": False, "seed": 42 + rep,
                   "stream_options": {"include_usage": True}}
        payload.update(sampler)
        if extra:
            payload.update(extra)
        t0 = time.time()
        r = httpx.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=payload, timeout=1800)
        wall = time.time() - t0
        if r.status_code != 200:
            out.append({"rep": rep, "http": r.status_code, "err": r.text[:200], "wall_s": round(wall, 1)})
            continue
        j = r.json()
        msg = j["choices"][0]["message"]
        out.append({
            "rep": rep, "finish_reason": j["choices"][0].get("finish_reason"),
            "content": (msg.get("content") or "")[:400],
            "content_len": len(msg.get("content") or ""),
            "reasoning_len": len(msg.get("reasoning_content") or ""),
            "reasoning_tail": (msg.get("reasoning_content") or "")[-120:],
            "usage": j.get("usage"), "wall_s": round(wall, 1),
        })
    return out


def raw_completion(port, prompt, n_predict=2048, sampler=None):
    payload = {"prompt": prompt, "n_predict": n_predict, "stream": False, "cache_prompt": False,
               "temperature": 0.0, "seed": 42}
    if sampler:
        payload.update(sampler)
    r = httpx.post(f"http://127.0.0.1:{port}/completion", json=payload, timeout=1800)
    r.raise_for_status()
    j = r.json()
    content = j.get("content", "")
    return {"n_predict": n_predict, "stop_type": j.get("stop_type"), "stop": j.get("stop"),
            "generated_chars": len(content), "has_think_open": "<think>" in prompt + content,
            "think_close_pos": content.find("</think>"),
            "content_after_think": content[content.find("</think>") + 8:][:300] if "</think>" in content else None,
            "content_head": content[:200], "content_tail": content[-160:], "usage": j.get("usage")}


def main():
    model = sys.argv[1]
    gpu = sys.argv[2]
    port = int(sys.argv[3])
    key = sys.argv[4]
    EVID.mkdir(parents=True, exist_ok=True)
    rec = {"key": key, "model": model, "gpu": gpu, "runtime": IMAGE, "sections": {}}

    name = f"rc-{key}"
    boot(name, gpu, model, port)
    try:
        # ---- A. apply-template ----
        A = {}
        for tid, kwargs in [("T1_default", None), ("T2_think_on", {"enable_thinking": True}),
                            ("T3_think_off", {"enable_thinking": False})]:
            j = apply_template(port, [{"role": "user", "content": ZH_PROBE}], kwargs)
            txt = j.get("prompt") or json.dumps(j, ensure_ascii=False)
            A[tid] = {"sha256": hashlib.sha256(txt.encode()).hexdigest(),
                      "tail": txt[-220:], "has_think": "<think>" in txt,
                      "think_closed_in_prompt": "</think>" in txt, "len": len(txt)}
        rec["sections"]["apply_template"] = A
        print("A:", {k: (v["has_think"], v["think_closed_in_prompt"]) for k, v in A.items()}, flush=True)

        # ---- B. raw /completion with the exact default-templated prompt ----
        t1 = apply_template(port, [{"role": "user", "content": ZH_PROBE}], None)
        prompt1 = t1.get("prompt")
        B = {"template_prompt_tail": prompt1[-160:]}
        for npred in (2048, 8192):
            B[f"greedy_np{npred}"] = raw_completion(port, prompt1, n_predict=npred)
            print(f"B raw np{npred}: think_close_pos={B[f'greedy_np{npred}']['think_close_pos']} stop={B[f'greedy_np{npred}']['stop_type']}", flush=True)
        rec["sections"]["raw_completion"] = B

        # ---- C. budget gradient via chat API (greedy, thinking on default; adaptive) ----
        C = {}
        for probe_name, probe in [("zh", ZH_PROBE), ("tcp", TCP_PROBE), ("coding", CODE_PROBE)]:
            stopped_at = None
            for budget in (1024, 4096, 8192, 16384):
                reps = 3 if budget <= 8192 else (1 if stopped_at is None else 0)
                if reps == 0:
                    continue
                res = chat_full(port, [{"role": "user", "content": probe}], budget, {"temperature": 0.0}, reps=reps)
                C[f"{probe_name}_b{budget}"] = res
                last = res[-1]
                print(f"C {probe_name} b{budget}: finish={last.get('finish_reason')} content_len={last.get('content_len')} reasoning_len={last.get('reasoning_len')}", flush=True)
                if last.get("finish_reason") == "stop" and last.get("content_len", 0) > 20:
                    stopped_at = budget
                    break
            C[f"{probe_name}_terminated_at"] = stopped_at
        rec["sections"]["budget_gradient"] = C

        # ---- D. sampler fairness (budget 8192) ----
        D = {}
        for sname, sampler in [("fair_greedy", {"temperature": 0.0}),
                               ("qwen_recommended_t06", QWEN_SAMPLER)]:
            for probe_name, probe in [("zh", ZH_PROBE), ("coding", CODE_PROBE)]:
                D[f"{sname}_{probe_name}"] = chat_full(port, [{"role": "user", "content": probe}], 8192, sampler, reps=3)
                last = D[f"{sname}_{probe_name}"][-1]
                print(f"D {sname} {probe_name}: content_len={last.get('content_len')} reasoning_len={last.get('reasoning_len')}", flush=True)
        rec["sections"]["sampler_fairness"] = D
    finally:
        kill(name)

    # ---- E. server-flag matrix (restarts) ----
    E = {}
    flag_sets = [
        ("reasoning_on", "--reasoning on"),
        ("reasoning_off", "--reasoning off"),
        ("reasoning_auto", "--reasoning auto"),
        ("reasoning_budget512", "--reasoning on --reasoning-budget 512"),
        ("reasoning_budget1024", "--reasoning on --reasoning-budget 1024"),
        ("reasoning_budget2048", "--reasoning on --reasoning-budget 2048"),
    ]
    for fname, flags in flag_sets:
        cname = f"rc-{key}-{fname}"
        try:
            boot(cname, gpu, model, port, extra=flags)
            ent = {"flags": flags}
            # verify what the template now produces
            j = apply_template(port, [{"role": "user", "content": TCP_PROBE}], None)
            txt = j.get("prompt") or ""
            ent["template_think_closed"] = "</think>" in txt
            ent["template_tail"] = txt[-160:]
            ent["probes"] = {}
            for probe_name, probe in [("tcp", TCP_PROBE), ("coding", CODE_PROBE)]:
                budget = 4096
                ent["probes"][probe_name] = chat_full(port, [{"role": "user", "content": probe}], budget,
                                                      {"temperature": 0.0}, reps=2)
                last = ent["probes"][probe_name][-1]
                print(f"E {fname} {probe_name}: finish={last.get('finish_reason')} content_len={last.get('content_len')} reason_len={last.get('reasoning_len')}", flush=True)
            E[fname] = ent
        except Exception as ex:
            E[fname] = {"flags": flags, "error": str(ex)[:300]}
        finally:
            kill(cname)
    rec["sections"]["server_flags"] = E

    lab.write_json(EVID / f"{key}-recon.json", rec)
    print("RECON DONE ->", EVID / f"{key}-recon.json")


if __name__ == "__main__":
    main()
