"""screening.py — Stage-1 four-model screening on the frozen BENCHMARK-RUNTIME.

Uniform config: FA on, KV q4_0/q4_0, batch/ubatch 512, -c 65536, -ngl 999,
--jinja, MTP OFF, greedy (temperature 0, seed fixed). Probes are machine-judged:
zh / coding(exec-tested) / strict-json(schema) / tool-call / math / needle@32K/64K,
plus 3x restart stability, VRAM, TTFT, prompt/decode TPS, thinking-token counts.
Output: evidence runs/stage1/<key>.json
"""
from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

MODELS = {
    "A-ista-gsq-iq3s-mtp": {
        "path": "/labmodels/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf",
        "repo": "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF@d562806",
        "quant": "GSQ-RCO IQ3_S(-mtp) 3.50bpw",
        "role": "BASE CONTROL",
    },
    "B-swift15-gsq-iq3s-mtp": {
        "path": "/labmodels/ukisai-swift15-gsq/Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf",
        "repo": "ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF@d74895b",
        "quant": "GSQ-RCO IQ3_S(-mtp) 3.50bpw",
        "role": "LONGCTX CANDIDATE",
    },
    "C-swift15-q5km": {
        "path": "/labmodels/ukisai-swift15/Swift-1.5-Qwen3.8-27B-Q5_K_M.gguf",
        "repo": "ukisai/Swift-1.5-Qwen3.8-27B-GGUF@a161446",
        "quant": "Q5_K_M 5.5bpw",
        "role": "QUALITY/CODING PRIMARY",
    },
    "D-swift10-q4km": {
        "path": "/labmodels/ukisai-swift10/Swift-Qwen3.8-27B-Q4_K_M.gguf",
        "repo": "ukisai/Swift-Qwen3.8-27B-GGUF@f8b396d",
        "quant": "Q4_K_M ~4.8bpw",
        "role": "REGRESSION CONTROL",
    },
}

RT = {"image": None, "name": "bench-runtime"}  # filled from CLI (frozen runtime)


def server_cmd(path: str, ctx: int, extra: str = "") -> str:
    return (f"-m {path} --host 0.0.0.0 --port 8080 -c {ctx} -np 1 -ngl 999 "
            f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a stage1 "
            f"-b 512 -ub 512 --metrics {extra}")


ROMAN_TESTS = [("III", 3), ("LVIII", 58), ("MCMXCIV", 1994), ("MMXXVI", 2026), ("CDXLIV", 444)]


def probe_coding(port: int) -> dict:
    q = ("写一个 Python 函数 romanToInt(s: str) -> int，把罗马数字字符串转换为整数（范围 1..3999）。"
         "只输出一个 ```python 代码块，不要其他解释。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=1500, temperature=0.0, seed=42)
    m = re.search(r"```python\n(.*?)```", r["text"], re.S)
    passed, detail = 0, "no code block"
    if m:
        code = m.group(1)
        cases = "; ".join(f"assert romanToInt({s!r})=={v}" for s, v in ROMAN_TESTS)
        runner = f"{code}\n{cases}\nprint('ALL_OK')"
        p = subprocess.run([sys.executable, "-I", "-c", runner], capture_output=True, text=True, timeout=60)
        passed = 1 if p.returncode == 0 and "ALL_OK" in p.stdout else 0
        detail = (p.stdout + p.stderr).strip()[:300]
    return {"pass": passed, "detail": detail, "wall_s": r["wall_s"], "usage": r["usage"], "reasoning_chars": r["reasoning_chars"]}


def probe_json(port: int) -> dict:
    import jsonschema
    r = lab.chat(port, [{"role": "user", "content": '返回严格 JSON 对象：{"ok": true, "count": 7, "items": ["x","y","z"], "nested": {"flag": false}}。不要输出任何其他文字。'}],
                  max_tokens=300, temperature=0.0, seed=42, extra={"response_format": {"type": "json_object"}})
    schema = {"type": "object", "properties": {"ok": {"const": True}, "count": {"const": 7},
              "items": {"type": "array", "items": {"type": "string"}, "minItems": 3},
              "nested": {"type": "object", "properties": {"flag": {"const": False}}}}, "required": ["ok", "count", "items", "nested"]}
    ok, err = 0, ""
    try:
        jsonschema.validate(json.loads(r["text"].strip()), schema)
        ok = 1
    except Exception as e:
        err = str(e)[:200]
    return {"pass": ok, "err": err, "text_head": r["text"][:120], "wall_s": r["wall_s"]}


def probe_tool(port: int) -> dict:
    tools = [{"type": "function", "function": {"name": "get_weather", "description": "query weather of a city",
              "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "unit": {"enum": ["c", "f"]}},
                             "required": ["city"]}}}]
    try:
        msg = lab.chat_nonstream(port, [{"role": "user", "content": "查一下北京现在的天气，用摄氏度。"}],
                                 extra={"tools": tools, "tool_choice": "auto"})
    except Exception as e:
        return {"pass": 0, "err": f"http {e}"}
    calls = msg.get("tool_calls") or []
    ok = 0
    detail = {"tool_calls": calls[:2]}
    if calls:
        fn = calls[0].get("function", {})
        if fn.get("name") == "get_weather":
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if args.get("city", "").find("北京") >= 0:
                    ok = 1
            except Exception:
                pass
    return {"pass": ok, "detail": detail}


def probe_math(port: int) -> dict:
    q = ("一个仓库有三批货物：第一批 1248 箱，第二批比第一批多 376 箱，第三批是前两批总和的一半少 115 箱。"
         "三批共多少箱？只输出最终数字。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=1200, temperature=0.0, seed=42)
    nums = re.findall(r"\d+", r["text"].replace(",", ""))
    ans = 1248 + (1248 + 376) + ((1248 + 1248 + 376) // 2 - 115)
    ok = 1 if str(ans) in nums else 0
    return {"pass": ok, "expected": ans, "nums_seen": nums[-5:], "reasoning_chars": r["reasoning_chars"],
            "usage": r["usage"], "wall_s": r["wall_s"]}


def probe_zh(port: int, nothink: bool = False) -> dict:
    extra = {"chat_template_kwargs": {"enable_thinking": False}} if nothink else None
    r = lab.chat(port, [{"role": "user", "content": "用中文向新同事解释：什么是 LLM 推理中的 KV cache？为什么量化它能省显存？200 字左右。"}],
                 max_tokens=3072, temperature=0.0, seed=42, extra=extra)
    t = r["text"]
    han = len(re.findall(r"[\u4e00-\u9fff]", t))
    # repetition loop check: any 16-char window appearing >=3 times
    loop = 0
    for i in range(0, max(len(t) - 16, 0), 8):
        w = t[i:i + 16]
        if len(w) == 16 and t.count(w) >= 3:
            loop = 1
            break
    key = "zh_nothink" if nothink else "zh"
    return {"key": key, "pass": 1 if han >= 80 and loop == 0 else 0, "han_chars": han, "loop": loop,
            "content_empty": 1 if han == 0 else 0, "reasoning_chars": r["reasoning_chars"],
            "text_head": t[:150], "usage": r["usage"], "wall_s": r["wall_s"]}


def needle_prompt(port: int, filler: str, depth: float, target_tokens: int, needle: str, question: str):
    sub, n = lab.cut_to_tokens(filler, port, target_tokens)
    pos = int(len(sub) * depth)
    doc = sub[:pos] + f"\n{needle}\n" + sub[pos:]
    return [{"role": "user", "content": doc + f"\n\n{question}"}], n


def probe_needle(port: int, filler: str, target: int, depth: float) -> dict:
    needle = "【内部备忘】本次评审会议的临时密码是 X7K9-42ZQ，会后立即作废。"
    msgs, n = needle_prompt(port, filler, depth, target, needle, "上文中的会议临时密码是什么？只输出密码本身。")
    t0 = time.time()
    r = lab.chat(port, msgs, max_tokens=600, temperature=0.0, seed=42)
    hit = 1 if "X7K9-42ZQ" in r["text"] else 0
    return {"pass": hit, "prompt_tokens": n, "depth": depth, "ttft_s": r["ttft_s"], "wall_s": r["wall_s"],
            "answer_head": r["text"][:80], "usage": r["usage"]}


def run_model(key: str, m: dict, image: str, gpu: str, port: int) -> dict:
    rec = {"model": key, **m, "image": image, "gpu": gpu, "ctx": 65536,
           "probes": {}, "restart": [], "tps": {}}
    cname = f"stage1-{key}"
    cmd = server_cmd(m["path"], 65536)
    lab._LASTLOG_POS.pop(cname, None)
    t_health = lab.server_up(cname, image, port, gpu, cmd)
    rec["first_health_s"] = round(t_health, 1)
    # settle + warmup (chat template / slot readiness on some builds lags health 200)
    time.sleep(2)
    for attempt in range(3):
        try:
            lab.chat_nonstream(port, [{"role": "user", "content": "ping"}], max_tokens=16)
            break
        except Exception:
            time.sleep(3)
    rec["vram_after_load"] = lab.vram_mib(gpu)
    # quality probes (each isolated so one failure keeps the rest + evidence)
    probes = [("zh", lambda: probe_zh(port)), ("zh_nothink", lambda: probe_zh(port, nothink=True)),
              ("coding_roman", lambda: probe_coding(port)), ("json_strict", lambda: probe_json(port)),
              ("tool_call", lambda: probe_tool(port)), ("math", lambda: probe_math(port))]
    filler = None
    try:
        filler, _ = lab.make_filler(65536 - 2048, port)
        probes += [("needle_32k_d50", lambda: probe_needle(port, filler, 32768 - 1024, 0.5)),
                   ("needle_64k_d50", lambda: probe_needle(port, filler, 65536 - 2048, 0.5))]
    except Exception as e:
        rec["filler_error"] = str(e)[:200]
    for pname, pfn in probes:
        try:
            rec["probes"][pname] = pfn()
        except Exception as e:
            rec["probes"][pname] = {"pass": 0, "error": str(e)[:250]}
        print(f"  probe {pname}: pass={rec['probes'][pname].get('pass')}", flush=True)
        # always-on evidence dump
        (lab.EVID / "runs" / "stage1").mkdir(parents=True, exist_ok=True)
        (lab.EVID / "runs" / "stage1" / f"{cname}-logs.txt").write_text(lab.docker_logs(cname)[-150000:])
    rec["tps"] = lab.parse_tps(cname)
    rec["vram_peak"] = lab.vram_mib(gpu)
    # restart x3
    for i in range(3):
        lab.server_down(cname)
        t = lab.server_up(cname, image, port, gpu, cmd)
        ok = 0
        try:
            r = lab.chat(port, [{"role": "user", "content": "1+1=? 只输出数字"}], max_tokens=200, temperature=0.0, seed=1)
            ok = 1 if "2" in r["text"][:20] else 0
        except Exception:
            pass
        rec["restart"].append({"cycle": i + 1, "health_s": round(t, 1), "sanity_ok": ok,
                               "vram": lab.vram_mib(gpu)})
    lab.write_json(lab.EVID / "runs" / "stage1" / f"{key}.json", rec)
    lab.server_down(cname)
    return rec


def main():
    image = sys.argv[1]
    gpu = sys.argv[2] if len(sys.argv) > 2 else "2"
    keys = sys.argv[3].split(",") if len(sys.argv) > 3 else list(MODELS)
    out = {}
    for i, k in enumerate(keys):
        port = 18111 + i
        print(f"=== stage1 {k} gpu{gpu} port {port}", flush=True)
        try:
            out[k] = run_model(k, MODELS[k], image, gpu, port)
        except Exception as e:
            out[k] = {"model": k, "error": str(e)[:500]}
            lab.server_down(f"stage1-{k}")
        lab.write_json(lab.EVID / "runs" / "stage1" / "stage1-summary.json", out)
    print(json.dumps({k: v.get("error") or {p: r.get("pass") for p, r in v.get("probes", {}).items()} for k, v in out.items()},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
