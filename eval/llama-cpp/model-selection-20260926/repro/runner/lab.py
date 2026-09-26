"""lab.py — harness core for llama.cpp model-selection-2026-09.

CPU-only. Controls isolated docker test servers via compose env, talks
OpenAI-compatible HTTP. Every run writes a self-describing JSON record
(task spec section 46 fields).
"""
from __future__ import annotations
import json, os, re, subprocess, time, hashlib, statistics
from datetime import datetime, timezone
from pathlib import Path

import httpx

LAB = Path("/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab")
EVID = Path("/data/tasks/qwen-model-lab/benchmarks/llama-cpp/model-selection-2026-09")
COMPOSE = LAB / "docker-compose.yml"

HOSTFACTS = json.loads((EVID / "environment.json").read_text())


def sh(cmd: list[str], timeout: int = 600, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def compose_env(name: str, image: str, port: int, gpu: str, cmd: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(LAB_NAME=name, LAB_IMAGE=image, LAB_PORT=str(port), LAB_GPU=gpu.split(",")[0], LAB_CMD=cmd)
    return env


def _server_up_run(name: str, image: str, port: int, gpu_csv: str, cmd: str) -> None:
    """Multi-GPU path: plain docker run (compose flow-seq can't take a variable list)."""
    sh(["docker", "rm", "-f", name], timeout=60)
    gpus_arg = "device=" + ",".join(g.strip() for g in gpu_csv.split(","))
    r = sh(["docker", "run", "-d", "--name", name, "--network", "llama-cpp-model-lab",
            "--gpus", f"\"{gpus_arg}\"", "-p", f"127.0.0.1:{port}:8080",
            "-v", "/data/models:/prodmodels:ro",
            "-v", "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/models:/labmodels:ro",
            "-v", "/data/tasks/qwen-model-lab/benchmarks/llama-cpp/model-selection-2026-09:/evidence:rw",
            "--restart", "no", image] + cmd.split(), timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"docker run failed for {name}: {r.stderr[-1500:]}")


def server_up(name: str, image: str, port: int, gpu: str, cmd: str) -> float:
    """Start test server; return wall seconds from container start to health 200."""
    t0 = time.time()
    if "," in gpu:
        _server_up_run(name, image, port, gpu, cmd)
    else:
        env = compose_env(name, image, port, gpu, cmd)
        print(f"    [lab] compose up {name} img={image} gpu={gpu} port={port}", flush=True)
        r = sh(["docker", "compose", "-p", f"llama-lab-{name.lower()}", "-f", str(COMPOSE), "up", "-d", "--force-recreate", "server"], timeout=300, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"compose up failed for {name}: {r.stderr[-2000:]}")
    print(f"    [lab] up done in {time.time()-t0:.1f}s, polling health", flush=True)
    deadline = time.time() + 1200
    last_err = None
    polls = 0
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5)
            if r.status_code == 200:
                return time.time() - t0
        except Exception as e:
            last_err = str(e)
        polls += 1
        if polls % 25 == 0:
            st = sh(["docker", "ps", "-a", "--filter", f"name={name}", "--format", "{{.Status}}"]).stdout.strip()
            print(f"    [lab] {name} poll#{polls} status={st!r} last_err={last_err}", flush=True)
        time.sleep(2)
    logs = sh(["docker", "logs", name, "--tail", "60"]).stdout
    raise RuntimeError(f"server {name} did not become healthy; status={st!r}; logs:\n{logs}")


def server_down(name: str) -> None:
    sh(["docker", "rm", "-f", name], timeout=120)
    _LASTLOG_POS.pop(name, None)


def docker_started_at(name: str) -> str:
    out = sh(["docker", "inspect", name, "--format", "{{.State.StartedAt}}"]).stdout.strip()
    return out


def docker_logs(name: str) -> str:
    r = sh(["docker", "logs", name], timeout=300)
    # llama-server logs to stderr; docker logs splits streams
    return (r.stdout or "") + (r.stderr or "")


def load_time_from_logs(name: str) -> dict:
    """Parse cold-start phases from llama-server logs (timestamps are RFC3339 with ms)."""
    logs = docker_logs(name)
    started = docker_started_at(name)
    ts = []
    for line in logs.splitlines():
        m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})Z", line)
        if m:
            ts.append(m.group(1))
    info = {"log_first_line": logs.splitlines()[1] if len(logs.splitlines()) > 1 else "",
            "container_started_at": started}
    m_load = re.search(r"load time\s*=\s*(\d+(?:\.\d+)?)\s*ms", logs)
    if m_load:
        info["model_load_ms"] = float(m_load.group(1))
    m_ml = re.search(r"^([\d.]+)\s+\w\s+srv\s+llama_server: model loaded", logs, re.M)
    if m_ml:
        info["model_loaded_at_stamp"] = m_ml.group(1)  # raw uptime stamp, e.g. 0.04.636.718
    m_warn = re.findall(r"cache_reuse is not supported[^\n]*", logs)
    if m_warn:
        info["warnings"] = m_warn[:2]
    for key, pat in {
        "listening": r"main: server is listening",
        "ggml_cuda_init": r"ggml_cuda_init: found",
        "offloaded_layers": r"offloaded \d+/",
    }.items():
        m = re.search(pat, logs)
        if m:
            info[f"first_{key}"] = m.group(0)[:160]
    info["cuda_devices"] = re.findall(r"ggml_cuda_init: found (\d+) CUDA devices", logs)
    info["compute_cap"] = re.findall(r"compute capability [\d.]+", logs)[:2]
    return info


_LASTLOG_POS: dict[str, int] = {}


def parse_tps(name: str, since_restart_marker: bool = True) -> dict:
    """Aggregate per-request eval stats from logs since last call."""
    logs = docker_logs(name)
    pos = _LASTLOG_POS.get(name, 0)
    new = logs[pos:]
    _LASTLOG_POS[name] = len(logs)
    out = {"prompt_tps": [], "decode_tps": [], "prompt_tokens": [], "gen_tokens": [], "prompt_ms": [], "eval_ms": []}
    for m in re.finditer(r"prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s+tokens\s*\(.*?([\d.]+)\s+tokens per second\)", new):
        out["prompt_ms"].append(float(m.group(1)))
        out["prompt_tokens"].append(int(m.group(2)))
        out["prompt_tps"].append(float(m.group(3)))
    for m in re.finditer(r"\|\s+eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s+tokens\s*\(.*?([\d.]+)\s+tokens per second\)", new):
        out["eval_ms"].append(float(m.group(1)))
        out["gen_tokens"].append(int(m.group(2)))
        out["decode_tps"].append(float(m.group(3)))
    return out


def vram_mib(gpu_index: str) -> dict:
    out = sh(["nvidia-smi", "--id", gpu_index, "--query-gpu=memory.used,utilization.gpu,power.draw,temperature.gpu",
              "--format=csv,noheader,nounits"]).stdout.strip()
    lines = [l for l in out.splitlines() if l.strip()]
    used, util, power, temp = [x.strip() for x in lines[0].split(",")]
    rec = {"vram_used_mib": int(used), "gpu_util_pct": int(util), "power_w": float(power), "temp_c": int(temp)}
    if len(lines) > 1:
        rec["per_gpu"] = [{"vram_used_mib": int(x.split(",")[0])} for x in lines]
        rec["vram_used_mib"] = sum(int(x.split(",")[0]) for x in lines)
    return rec


def tokenize(port: int, text: str) -> int:
    r = httpx.post(f"http://127.0.0.1:{port}/tokenize", json={"content": text}, timeout=300)
    r.raise_for_status()
    return len(r.json()["tokens"])


def chat(port: int, messages: list, max_tokens: int = 512, stream: bool = True, seed: int = 42,
         temperature: float = 0.0, extra: dict | None = None, timeout: float = 1800) -> dict:
    """One chat completion; measures TTFT (first chunk) and wall time; returns usage+text. Retries once."""
    try:
        return _chat_once(port, messages, max_tokens, stream, seed, temperature, extra, timeout)
    except (httpx.HTTPError, httpx.StreamError) as e:
        time.sleep(3)
        out = _chat_once(port, messages, max_tokens, stream, seed, temperature, extra, timeout)
        out["retried_after"] = str(e)[:120]
        return out


def _chat_once(port: int, messages: list, max_tokens: int, stream: bool, seed: int,
               temperature: float, extra: dict | None, timeout: float) -> dict:
    """One chat completion; measures TTFT (first chunk) and wall time; returns usage+text."""
    payload = {"messages": messages, "max_tokens": max_tokens, "stream": stream,
               "temperature": temperature, "seed": seed}
    if stream:
        payload["stream_options"] = {"include_usage": True}
    if extra:
        payload.update(extra)
    t0 = time.time()
    ttft = None
    text_parts: list[str] = []
    reasoning_chars = 0
    usage = {}
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", f"http://127.0.0.1:{port}/v1/chat/completions", json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                if ttft is None:
                    ttft = time.time() - t0
                choices = j.get("choices") or []
                if choices:
                    delta = choices[0].get("delta", {})
                    if delta.get("reasoning_content"):
                        reasoning_chars += len(delta["reasoning_content"])
                    if delta.get("content"):
                        text_parts.append(delta["content"])
                if j.get("usage"):
                    usage = j["usage"]
    wall = time.time() - t0
    text = "".join(text_parts)
    return {"ttft_s": round(ttft, 3) if ttft else None, "wall_s": round(wall, 3),
            "reasoning_chars": reasoning_chars,
            "completion_chars": len(text), "text": text, "usage": usage,
            "sha_output": hashlib.sha256(text.encode()).hexdigest()[:16]}


def chat_nonstream(port: int, messages: list, extra: dict | None = None, max_tokens: int = 300,
                   timeout: float = 600) -> dict:
    """Non-streaming chat completion (used for tool-call smoke; returns raw message object)."""
    payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.0, "seed": 1}
    if extra:
        payload.update(extra)
    r = httpx.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=payload, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"] if j.get("choices") else j


def make_filler(target_tokens: int, port: int, seed: int = 7) -> tuple[str, int]:
    """Deterministic mixed CN/EN filler corpus expanded to ~target tokens (verified via /tokenize)."""
    base = [
        "系统运维手册第{n}节：GPU 服务器的日常巡检包括驱动版本核对、显存水位记录、温度与功耗曲线归档，以及推理服务的健康探测。",
        "Release note {n}: fixed a race in the prefetch queue; the cache layer now evicts cold prefixes before admitting new sessions.",
        "第{n}条会议纪要：周五前完成压测报告，长上下文回归用例由值班同学补充，复盘时间另行通知。",
        "Ops runbook {n}: when the LB reports an unhealthy backend, drain sessions first, then inspect llama-server slots, never restart during prefill.",
    ]
    parts: list[str] = []
    n = 0
    cur = ""
    while len(cur) < target_tokens * 3.2:
        parts.append(base[n % len(base)].format(n=n))
        n += 1
        cur = "\n".join(parts)
    ntok = tokenize(port, cur)
    # ratio-based trim + refinement (2-3 tokenize calls total for the big corpus)
    if ntok > target_tokens:
        ratio = target_tokens / ntok
        cur = cur[: int(len(cur) * ratio * 1.02)]
        ntok = tokenize(port, cur)
        while ntok > target_tokens:
            cur = cur[: int(len(cur) * 0.995)]
            ntok = tokenize(port, cur)
    return cur, ntok


def cut_to_tokens(filler: str, port: int, target: int) -> tuple[str, int]:
    """Cut a prefix of filler to <= target tokens (keeps nesting for prefix cache)."""
    n = tokenize(port, filler)
    if n <= target:
        return filler, n
    ratio = target / n
    s = filler[: int(len(filler) * ratio * 1.02)]
    n = tokenize(port, s)
    while n > target:
        s = s[: int(len(s) * 0.995)]
        n = tokenize(port, s)
    return s, n


def run_record(**kw) -> dict:
    """§46-style base record."""
    rec = {
        "timestamp": now_iso(),
        "host": HOSTFACTS["hostname"],
        "nvidia_driver": HOSTFACTS["driver"],
        "gpu_model": "RTX 4090 24GB",
    }
    rec.update(kw)
    return rec


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
