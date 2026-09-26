"""longcode.py — LONG-CODE suite: repo-level comprehension + bug locate + patch, machine-scored.

Part 1  REAL-REPO: corpus = this workspace's public repo (already sanitized, bound for GitHub);
        questions have grep ground truth.
Part 2  SYNTH-REPO: deterministic 40-file Python/TS mini-project (~120K tokens) with planted
        defects; tasks = locate (string-match) + patch (exec-tested).
Usage: uv run python longcode.py <image> <gpu> <model_path> <model_key> <ctx> [port]
Output: evidence runs/long-code/<model_key>.json
"""
from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

REPO = Path("/data/tasks/qwen-model-lab/repo")


def real_repo_corpus() -> str:
    """Bundle key repo files (text only, size-capped) deterministically."""
    out = []
    for p in sorted(REPO.rglob("*")):
        if p.is_file() and p.suffix in {".md", ".yml", ".yaml", ".sh", ".py", ".conf", ".lua", ".json", ".txt"} \
           and ".git" not in p.parts and p.stat().st_size < 200_000:
            out.append(f"===== FILE {p.relative_to(REPO)} =====\n" + p.read_text(errors="replace")[:60_000])
    return "\n".join(out)


REAL_TASKS = [
    {"q": "生产 llama-server 容器（qwen27b）加载的 GGUF 文件名是什么？只输出文件名。", "gt": ["Qwen3.8-27B-coding-v1.1-iq4xs.gguf"]},
    {"q": "生产 llama-server 的 KV cache 的 K 和 V 分别用的什么量化类型？按 'K=x,V=y' 格式输出。", "gt": ["q4_0"]},
    {"q": "OpenResty LB 的路由逻辑在哪个 lua 文件？只输出文件名。", "gt": ["route.lua"]},
    {"q": "eval/spec_sandbox.sh 里 IMG 变量指定的镜像 tag 是什么？只输出 tag。", "gt": ["cuda12.4-b10715"]},
    {"q": "本仓库脱敏替换表一共有几条规则？只输出数字。", "gt": ["8"]},
    {"q": "生产栈里 OpenResty 容器名和监控容器名分别是什么？按 'lb=X,mon=Y' 输出。", "gt": ["qwen27b-lb", "qwen27b-mon"]},
    {"q": "docker-compose.yml 中 llama-server 的 --spec-type 是什么？只输出值。", "gt": ["draft-dflash"]},
    {"q": "生产 llama-server 的草稿模型（-md）文件名是什么？只输出文件名。", "gt": ["Qwen3.8-27B-DFlash2-Q4_K_M.gguf"]},
]


# ---------- synthetic repo ----------
def synth_repo(seed: int = 7, n_modules: int = 36, funcs_per_mod: int = 6) -> tuple[str, dict]:
    """Deterministic pseudo-code repo with a planted off-by-one bug and a config key mismatch."""
    import random
    rng = random.Random(seed)
    files: dict[str, str] = []
    words = ["fetch", "parse", "validate", "transform", "cache", "dispatch", "merge", "audit", "route", "score"]
    for m in range(n_modules):
        lines = [f'"""module {m}: generated service layer"""', "import logging", ""]
        for f in range(funcs_per_mod):
            w = words[(m + f) % len(words)]
            body = "\n".join(f"    x{x} = (value * {x+1}) % 97" for x in range(4 + (m % 3)))
            lines += [f"def {w}_{m}_{f}(value: int, factor: int = {f+2}) -> int:",
                      f"    # caller chain: {w}_{m}_{f} used by dispatch_{m}",
                      body, f"    return x0 + factor", ""]
        files.append((f"src/mod_{m:02d}.py", "\n".join(lines)))
    # planted bug: backoff off-by-one in utils/backoff.py
    files.append(("src/utils/backoff.py",
        'def calculate_retry_backoff(attempt: int, base_ms: int = 100) -> int:\n'
        '    """Exponential backoff; attempt=1 -> 100ms, attempt=2 -> 200ms ..."""\n'
        '    return base_ms * (2 ** attempt)\n'  # BUG: attempt=1 gives 200ms (spec says 100ms)
        ))
    # config mismatch: config says max_conn, code reads max_connections
    files.append(("config/settings.py", 'MAX_CONN = 64\nTIMEOUT_MS = 5000\n'))
    files.append(("src/pool.py", 'from config.settings import MAX_CONNECTIONS  # planted mismatch\n'))
    doc = "\n".join(f"===== FILE {name} =====\n{src}" for name, src in files)
    gt = {"bug_file": "src/utils/backoff.py", "config_key": "MAX_CONN", "importer": "src/pool.py"}
    return doc, gt


def synth_tasks(gt: dict) -> list[dict]:
    return [
        {"q": "这个工程里 calculate_retry_backoff 定义在哪个文件？只输出文件路径。", "need": [gt["bug_file"]]},
        {"q": "calculate_retry_backoff 的规格：attempt=1 应返回 base_ms 本身。当前实现有什么 bug？"
              "回答包含'应该改成 base_ms * (2 ** (attempt - 1))'或等价描述与所在文件。", "need": ["backoff"]},
        {"q": "src/pool.py 导入的配置键与 config/settings.py 中实际定义的键不一致。"
              "分别指出导入的键名和实际定义的键名，格式 'imported=X, defined=Y'。", "need": ["MAX_CONNECTIONS", "MAX_CONN"]},
        {"q": "列出 mod_00 到 mod_05 中函数名前缀为 dispatch 的函数名（带下标）。", "need": ["dispatch_"]},
    ]


def patch_task(port: int) -> dict:
    q = ("修复以下函数使其满足：attempt=1 时返回 100，attempt=2 返回 200，attempt=3 返回 400（base_ms=100）。"
         "只输出修复后的完整 Python 函数，放在 ```python 代码块里。\n\n"
         "def calculate_retry_backoff(attempt: int, base_ms: int = 100) -> int:\n    return base_ms * (2 ** attempt)")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=1200, temperature=0.0, seed=42)
    m = re.search(r"```python\n(.*?)```", r["text"], re.S)
    if not m:
        return {"pass": 0, "err": "no code block"}
    code = m.group(1)
    tests = "rs=[calculate_retry_backoff(a) for a in (1,2,3,5)]\nassert rs==[100,200,400,1600], rs\nprint('PATCH_OK')"
    p = subprocess.run([sys.executable, "-I", "-c", code + "\n" + tests], capture_output=True, text=True, timeout=60)
    return {"pass": 1 if p.returncode == 0 else 0, "detail": (p.stdout + p.stderr).strip()[:200], "wall_s": r["wall_s"]}


def main():
    image, gpu, model_path, key, ctx = sys.argv[1:6]
    ctx = int(ctx)
    port = int(sys.argv[6]) if len(sys.argv) > 6 else 18141
    cname = f"longcode-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c {ctx} -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a longcode "
           f"-b 1024 -ub 1024 --metrics")
    rec = {"model": key, "ctx": ctx, "image": image, "tasks": []}
    lab.server_up(cname, image, port, gpu, cmd)
    rec["vram_after_load"] = lab.vram_mib(gpu)
    time.sleep(2)
    for attempt in range(3):
        try:
            lab.chat_nonstream(port, [{"role": "user", "content": "ping"}], max_tokens=16)
            break
        except Exception:
            time.sleep(3)
    # PART 1: real repo (truncate to fit ctx with margin; server counts ~2K above client)
    repo_doc = real_repo_corpus()
    n_repo = lab.tokenize(port, repo_doc)
    while n_repo > ctx - 4096 and len(repo_doc) > 10000:
        repo_doc = repo_doc[: int(len(repo_doc) * (ctx - 6144) / n_repo)]
        n_repo = lab.tokenize(port, repo_doc)
    rec["repo_doc_tokens"] = n_repo
    print(f"repo corpus tokens: {n_repo}", flush=True)
    for t in REAL_TASKS:
        r = lab.chat(port, [{"role": "user", "content": repo_doc + "\n\n" + t["q"]}],
                     max_tokens=700, temperature=0.0, seed=42)
        ok = 1 if all(g.lower() in r["text"].lower() for g in t["gt"]) else 0
        rec["tasks"].append({"part": "real-repo", "q": t["q"], "pass": ok, "answer": r["text"][:150],
                             "wall_s": r["wall_s"], "reasoning_chars": r["reasoning_chars"]})
        print(f"  real: {t['q'][:24]}... pass={ok}", flush=True)
    # PART 2: synth repo (bounded by ctx)
    synth_doc, gt = synth_repo()
    n_syn = lab.tokenize(port, synth_doc)
    while n_syn > ctx - 4096 and len(synth_doc) > 10000:
        synth_doc = synth_doc[: int(len(synth_doc) * (ctx - 6144) / n_syn)]
        n_syn = lab.tokenize(port, synth_doc)
    rec["synth_doc_tokens"] = n_syn
    for t in synth_tasks(gt):
        r = lab.chat(port, [{"role": "user", "content": synth_doc + "\n\n" + t["q"]}],
                     max_tokens=900, temperature=0.0, seed=42)
        ok = 1 if all(g.lower() in r["text"].lower() for g in t["need"]) else 0
        rec["tasks"].append({"part": "synth-locate", "q": t["q"][:60], "pass": ok, "answer": r["text"][:150],
                             "wall_s": r["wall_s"]})
        print(f"  synth: pass={ok}", flush=True)
    rec["patch"] = patch_task(port)
    print("  patch:", rec["patch"]["pass"], flush=True)
    rec["tps"] = lab.parse_tps(cname)
    rec["vram_peak"] = lab.vram_mib(gpu)
    (lab.EVID / "runs" / "long-code").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "long-code" / f"{key}.json", rec)
    lab.server_down(cname)
    print(json.dumps({"real": sum(t["pass"] for t in rec["tasks"] if t["part"] == "real-repo"),
                      "synth": sum(t["pass"] for t in rec["tasks"] if t["part"] == "synth-locate"),
                      "patch": rec["patch"]["pass"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
