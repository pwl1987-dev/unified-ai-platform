#!/usr/bin/env python3
"""nextgen 基准 harness — Phase 00+ 规范客户端（替代 dig028 bench_conc.py 口径）。

冻结公式（METRICS-SCHEMA.md §1，评审 v2.1 第 4 条）：
  ttfb_s                       = first_header  - request_start
  ttft_s                       = first_token   - request_start
  e2e_output_tok_s             = output_tokens / (last_token - request_start)
  client_observed_decode_tok_s = (output_tokens - 1) / (last_token - first_token)
  tpot_s                       = (last_token - first_token) / (output_tokens - 1)
  aggregate_output_tok_s(C>1)  = sum(output_tokens) / (batch_end - batch_start)
* output_tokens<2 => decode/TPOT 为 null + INSUFFICIENT_TOKENS（禁 0/NaN）
* client_observed_* 是客户端观测值，含 HTTP/SSE/调度抖动，不等同 engine decode
* per-token 时间戳内存收集、run 结束后一次性落盘（不在 decode 中刷盘）
* /metrics 100ms、NVML 500ms 采样独立线程，记录实际间隔/缺失率/退出码
* fixed-output：ignore_eos=true；requested==completion==N 断言，早停样本单列

夹具构造与 dig028 bench_conc.py 逐字节一致：make_prompt(target)（仓库相对路径导入
inference/vllm/bench/ulmus_validate.py，无本机绝对路径依赖）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))  # .../qwen3.8-27b-8x4090-stack
NEXTGEN = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "inference", "vllm", "bench"))
sys.path.insert(0, HERE)

from ulmus_validate import make_prompt  # noqa: E402  冻结的夹具构造（历史同源）
from sseparser import SSEParser, extract_content, extract_finish_reason  # noqa: E402
import nvml_bind  # noqa: E402

SCHEMA_VERSION = "nextgen-metrics-1"
CLIENT_VERSION = "bench_nextgen-1"
HARNESS_FILES = ["bench_nextgen.py", "sseparser.py", "nvml_bind.py"]


def git_sha() -> str:
    try:
        return subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 指标计算（纯函数 — 单元测试喂合成时间戳）
# ---------------------------------------------------------------------------

def compute_request_metrics(ev: dict) -> dict:
    """ev: {request_start, first_header, first_token, token_ts[], last_token,
    output_tokens, early_stop, stop_reason}（全部 monotonic 秒）。"""
    out = {
        "request_index": ev.get("request_index"),
        "ok": ev.get("ok", False),
        "ttfb_s": None, "ttft_s": None, "e2e_latency_s": None,
        "output_tokens": ev.get("output_tokens"),
        "e2e_output_tok_s": None,
        "client_observed_decode_tok_s": None,
        "tpot_s": None,
        "null_reason": None,
        "early_stop": ev.get("early_stop", False),
        "stop_reason": ev.get("stop_reason"),
    }
    if not ev.get("ok"):
        return out
    rs, fh, ft, lt = (ev.get(k) for k in
                      ("request_start", "first_header", "first_token", "last_token"))
    n = ev.get("output_tokens") or 0
    if fh is not None:
        out["ttfb_s"] = round(fh - rs, 4)
    if ft is not None:
        out["ttft_s"] = round(ft - rs, 4)
    if lt is not None:
        out["e2e_latency_s"] = round(lt - rs, 4)
        if n >= 1:
            out["e2e_output_tok_s"] = round(n / (lt - rs), 3)
        if ft is not None and n >= 2:
            decode_s = lt - ft
            out["client_observed_decode_tok_s"] = round((n - 1) / decode_s, 3)
            out["tpot_s"] = round(decode_s / (n - 1), 6)
        elif n < 2:
            out["null_reason"] = "INSUFFICIENT_TOKENS"
    return out


def compute_percentiles_if_enough(per_req: list[dict], min_samples: int = 20) -> dict:
    """样本层才报分位数；<min_samples 返回空对象（两层口径，禁混用）。"""
    if len(per_req) < min_samples:
        return {}
    def pct(vals, q):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return None
        k = max(0, min(len(vals) - 1, round(q * (len(vals) - 1))))
        return round(vals[k], 4)
    ttfts = [r["ttft_s"] for r in per_req if r.get("ok")]
    tpots = [r["tpot_s"] for r in per_req if r.get("ok")]
    return {"ttft_p50_s": pct(ttfts, 0.50), "ttft_p95_s": pct(ttfts, 0.95),
            "ttft_p99_s": pct(ttfts, 0.99),
            "tpot_p50_s": pct(tpots, 0.50), "tpot_p95_s": pct(tpots, 0.95),
            "tpot_p99_s": pct(tpots, 0.99)}


# ---------------------------------------------------------------------------
# /metrics 采样线程（100ms 冻结）
# ---------------------------------------------------------------------------

KNOWN_GAUGES = {
    "vllm:num_requests_running": "num_requests_running",
    "vllm:num_requests_waiting": "num_requests_waiting",
    "vllm:gpu_cache_usage_perc": "gpu_cache_usage_perc",
    "vllm:num_preemptions": "num_preemptions_total",
    "vllm:prefix_cache_queries": "prefix_cache_queries_total",
    "vllm:prefix_cache_hits": "prefix_cache_hits_total",
    "vllm:token_usage": "token_usage_perc",
}


class MetricsSampler(threading.Thread):
    def __init__(self, metrics_url: str, interval_ms: int = 100):
        super().__init__(daemon=True)
        self.url, self.interval_ms = metrics_url, interval_ms
        self.samples: list[dict] = []
        self._halt = threading.Event()
        self.exit_code = 0
        self.errors: list[str] = []

    def run(self) -> None:
        while not self._halt.is_set():
            t0 = time.monotonic_ns()
            try:
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    body = r.read().decode("utf-8", "replace")
                parsed = {}
                raw_kept = []
                for ln in body.splitlines():
                    if not ln.startswith("vllm:"):
                        continue
                    raw_kept.append(ln)
                    parts = ln.rsplit(" ", 1)
                    key = parts[0].split("{")[0] if len(parts) == 2 else None
                    if key in KNOWN_GAUGES:
                        try:
                            parsed[KNOWN_GAUGES[key]] = float(parts[1])
                        except ValueError:
                            pass
                self.samples.append({"t_mono_ns": time.monotonic_ns(),
                                     "t_utc_ns": time.time_ns(),
                                     "parsed": parsed, "vllm_lines": raw_kept})
            except Exception as e:  # noqa: BLE001
                self.exit_code = 1
                self.errors.append(str(e)[:200])
                if len(self.errors) > 20:
                    break
            wait_s = max(0.0, self.interval_ms / 1000 - (time.monotonic_ns() - t0) / 1e9)
            self._halt.wait(wait_s)

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=10)

    def stats(self) -> dict:
        ts = [s["t_mono_ns"] for s in self.samples]
        gaps_ms = [(b - a) / 1e6 for a, b in zip(ts, ts[1:])] if len(ts) > 1 else []
        missing = sum(1 for g in gaps_ms if g > 2 * self.interval_ms)
        return {
            "requested_interval_ms": self.interval_ms,
            "actual_interval_ms_min": round(min(gaps_ms), 1) if gaps_ms else None,
            "actual_interval_ms_median": round(statistics.median(gaps_ms), 1) if gaps_ms else None,
            "actual_interval_ms_max": round(max(gaps_ms), 1) if gaps_ms else None,
            "missing_sample_ratio": round(missing / len(gaps_ms), 4) if gaps_ms else None,
            "max_gap_ms": round(max(gaps_ms), 1) if gaps_ms else None,
            "sampler_exit_code": self.exit_code,
            "samples_collected": len(self.samples),
            "errors": self.errors[:5],
        }

    def max_running(self) -> int | None:
        vals = [s["parsed"].get("num_requests_running") for s in self.samples]
        vals = [v for v in vals if v is not None]
        return int(max(vals)) if vals else None


# ---------------------------------------------------------------------------
# 请求执行
# ---------------------------------------------------------------------------

def canonical_sha(payload_wo_salt: dict) -> str:
    return sha256_str(json.dumps(payload_wo_salt, sort_keys=True, ensure_ascii=False))


def run_one(api: str, args, prompt: str, idx: int, barrier: threading.Barrier,
            shared: dict) -> None:
    mono, utc = time.monotonic_ns, time.time_ns
    salt = f"{args.salt_namespace}-{args.salt_key}-{idx}"
    body: dict = {
        "model": "qwen3.8-27b", "temperature": 0, "seed": args.seed,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.max_tokens, "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": salt,
    }
    if args.mode == "fixed-output":
        body["ignore_eos"] = True
    canonical = {k: v for k, v in body.items() if k != "cache_salt"}
    csha = canonical_sha(canonical)

    rec = {
        "experiment_id": args.experiment_id, "request_index": idx,
        "client_version": CLIENT_VERSION,
        "request_start_mono_ns": None, "request_start_utc_ns": None,
        "sampling": {"temperature": body["temperature"], "seed": body["seed"],
                     "stream": True, "max_tokens": body["max_tokens"],
                     "mode": args.mode, "ignore_eos": body.get("ignore_eos", False),
                     "enable_thinking": False},
        "fixture": {"name": args.fixture_name, "sha256": args.fixture_sha,
                    "actual_input_tokens": None},
        "canonical_request_sha256": csha, "cache_salt": salt,
        "cache_salt_namespace": args.salt_namespace,
        "events": [], "outcome": {"ok": False},
    }
    m = {"request_index": idx, "ok": False, "output_tokens": None,
         "early_stop": False, "stop_reason": None,
         "request_start": None, "first_header": None, "first_token": None,
         "last_token": None, "token_ts": []}

    barrier.wait()
    t0m, t0u = mono(), utc()
    rec["request_start_mono_ns"], rec["request_start_utc_ns"] = t0m, t0u
    m["request_start"] = t0m / 1e9
    rec["events"].append({"t_mono_ns": t0m, "t_utc_ns": t0u, "kind": "request_start"})

    ntok, usage, finish = 0, None, None
    parser = SSEParser()
    try:
        req = urllib.request.Request(
            api + "/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=args.timeout_s)
        t_hdr = mono()
        m["first_header"] = t_hdr / 1e9
        rec["events"].append({"t_mono_ns": t_hdr, "t_utc_ns": utc(), "kind": "first_header",
                              "http_status": resp.status})
        first_byte_seen = False
        while True:
            line = resp.readline()
            if not line:
                break
            if not first_byte_seen:
                first_byte_seen = True
                rec["events"].append({"t_mono_ns": mono(), "t_utc_ns": utc(),
                                      "kind": "first_byte"})
            for ev in parser.feed(line):
                if ev["kind"] != "data" or ev.get("malformed"):
                    if ev["kind"] == "done":
                        rec["events"].append({"t_mono_ns": mono(), "t_utc_ns": utc(),
                                              "kind": "done"})
                    continue
                obj = ev["json"]
                c = extract_content(obj)
                if c:
                    t_tok = mono()
                    ntok += 1
                    if m["first_token"] is None:
                        m["first_token"] = t_tok / 1e9
                        rec["events"].append({"t_mono_ns": t_tok, "t_utc_ns": utc(),
                                              "kind": "first_token"})
                    m["token_ts"].append(t_tok / 1e9)
                    m["last_token"] = t_tok / 1e9
                fr = extract_finish_reason(obj)
                if fr:
                    finish = fr
                if obj.get("usage"):
                    usage = obj["usage"]
        parser.flush()
        t_end = mono()
        if m["last_token"] is not None:
            rec["events"].append({"t_mono_ns": int(m["last_token"] * 1e9),
                                  "t_utc_ns": utc(), "kind": "last_token"})
        server_ct = (usage or {}).get("completion_tokens")
        output_tokens = server_ct if server_ct is not None else ntok
        early = bool(args.mode == "fixed-output" and output_tokens is not None
                     and output_tokens < args.max_tokens)
        m.update({"ok": True, "output_tokens": output_tokens,
                  "early_stop": early, "stop_reason": finish})
        # spec decode 下一个 SSE chunk 可含多 token：ntok 是事件数不是 token 数。
        # 退化性不一致（服务端有 token 客户端零事件，或反之）才计 mismatch。
        degenerate = bool((server_ct or 0) > 0 and ntok == 0) or bool(
            server_ct is not None and server_ct == 0 and ntok > 0)
        rec["outcome"] = {
            "ok": True, "http_status": resp.status, "error": None,
            "client_event_count": ntok,
            "server_completion_tokens": server_ct,
            "server_prompt_tokens": (usage or {}).get("prompt_tokens"),
            "stop_reason": finish,
            "count_mismatch": degenerate,
            "early_stop": early,
        }
        if usage and usage.get("prompt_tokens") is not None:
            rec["fixture"]["actual_input_tokens"] = usage["prompt_tokens"]
            m["actual_input_tokens"] = usage["prompt_tokens"]
        rec["events"].append({"t_mono_ns": t_end, "t_utc_ns": utc(), "kind": "usage",
                              "client_wall_s": round((t_end - t0m) / 1e9, 4)})
    except urllib.error.HTTPError as e:
        rec["outcome"] = {"ok": False, "http_status": e.code, "error": f"HTTPError:{e.code}",
                          "client_event_count": ntok, "server_completion_tokens": None,
                          "stop_reason": None, "count_mismatch": False, "early_stop": False}
    except Exception as e:  # noqa: BLE001
        rec["outcome"] = {"ok": False, "http_status": None, "error": str(e)[:200],
                          "client_event_count": ntok, "server_completion_tokens": None,
                          "stop_reason": None, "count_mismatch": False, "early_stop": False}
        rec["events"].append({"t_mono_ns": mono(), "t_utc_ns": utc(), "kind": "error",
                              "error": str(e)[:200]})
    with shared["lock"]:
        shared["raw"].append(rec)
        shared["meta"].append(m)


# ---------------------------------------------------------------------------

FIXTURE_TARGETS = {"d565": 512, "p4k": 4096, "p32k": 32768,
                   "p128k": 131072, "p220k": 220000, "p238k": 238000}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="如 http://127.0.0.1:19701/v1")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--fixture", required=True,
                    help="d565|p4k|p32k|p128k|p220k|p238k|custom:<target_tokens>")
    ap.add_argument("--mode", choices=["fixed-output", "natural-stop"], required=True)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, required=True)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--timeout-s", type=int, default=900)
    ap.add_argument("--salt-namespace", default="formal", choices=["warmup", "formal"])
    ap.add_argument("--no-nvml", action="store_true",
                    help="对照实验：禁用 NVML 采样器，量化 nvidia-smi 轮询开销")
    ap.add_argument("--salt-key", default=None,
                    help="稳定 salt 键（暖前缀形态：跨 run 复用以命中 prefix cache；默认=experiment_id 唯一冷形态）")
    ap.add_argument("--out-dir", required=True, help="staging 实验目录")
    # server 身份（manifest 用）
    ap.add_argument("--port", type=int)
    ap.add_argument("--server-pid", type=int)
    ap.add_argument("--server-pgid", type=int)
    ap.add_argument("--tp", type=int, default=1)
    ap.add_argument("--ms", type=int, default=1)
    ap.add_argument("--cache-root")
    ap.add_argument("--gpu-uuids", help="逗号分隔本实验 GPU UUID 列表")
    ap.add_argument("--host-snapshot", default=os.path.join(NEXTGEN, "repro", "host-snapshot.json"))
    ap.add_argument("--env-lock", default=os.path.join(NEXTGEN, "repro", "env-lock.json"))
    args = ap.parse_args()
    if not args.salt_key:
        args.salt_key = args.experiment_id

    if args.fixture.startswith("custom:"):
        target = int(args.fixture.split(":", 1)[1])
        args.fixture_name = args.fixture
    else:
        target = FIXTURE_TARGETS[args.fixture]
        args.fixture_name = args.fixture
    prompt = make_prompt(target)
    args.fixture_sha = sha256_str(prompt)

    os.makedirs(args.out_dir, exist_ok=True)
    metrics_url = args.api.rsplit("/v1", 1)[0] + "/metrics"
    msamp = MetricsSampler(metrics_url, interval_ms=100)
    uuids = [u for u in (args.gpu_uuids or "").split(",") if u] or None
    if args.no_nvml:
        nsamp = nvml_bind.NVMLSampler(interval_ms=10**9, uuids=uuids or ["__none__"])
        nsamp.samples = []
        class _NS:  # 空采样器（对照实验：量化 nvidia-smi 轮询开销）
            samples = []
            def stop(self): pass
            def stats(self):
                return {"requested_interval_ms": None, "actual_interval_ms_median": None,
                        "missing_sample_ratio": None, "max_gap_ms": None,
                        "sampler_exit_code": 0, "samples_collected": 0,
                        "note": "disabled by --no-nvml (sampler-tax control run)"}
        nsamp = _NS()
    else:
        nsamp = nvml_bind.NVMLSampler(interval_ms=500, uuids=uuids)
        nsamp.start()
    msamp.start()

    shared = {"lock": threading.Lock(), "raw": [], "meta": []}
    barrier = threading.Barrier(args.concurrency)
    threads = []
    t_batch_launch = time.monotonic_ns()
    for i in range(args.concurrency):
        t = threading.Thread(target=run_one,
                             args=(args.api, args, prompt, i, barrier, shared))
        t.start(); threads.append(t)
        time.sleep(0.02)  # 错开微秒级启动抖动，barrier 负责对齐
    for t in threads:
        t.join()
    t_batch_end = time.monotonic_ns()
    msamp.stop(); nsamp.stop()

    raw = sorted(shared["raw"], key=lambda r: r["request_index"])
    meta = sorted(shared["meta"], key=lambda m: m["request_index"])

    per_req = [compute_request_metrics(m) for m in meta]
    ok_reqs = [r for r in per_req if r["ok"]]
    full_samples = [r for r in ok_reqs if not r["early_stop"]]
    # 性能统计只用完整样本；早停样本单列（fixed-output 完整性要求）
    perf_reqs = full_samples
    sum_tok = sum(r["output_tokens"] or 0 for r in perf_reqs)
    batch_wall_s = (t_batch_end - t_batch_launch) / 1e9
    agg = {"batch_wall_s": round(batch_wall_s, 3), "sum_output_tokens": sum_tok}
    if perf_reqs and sum_tok > 0:
        # batch 窗用请求真实起点/终点（barrier 后首请求起点到最后 token）
        starts = [m["request_start"] for m in meta if m["ok"]]
        ends = [m["last_token"] for m in meta if m["ok"] and m["last_token"]]
        if starts and ends:
            agg["batch_wall_s"] = round(max(ends) - min(starts), 3)
            agg["aggregate_output_tok_s"] = round(sum_tok / (max(ends) - min(starts)), 3)
    mr = msamp.max_running()
    agg["max_running_observed"] = mr
    if args.concurrency > 1:
        agg["resident_concurrency_valid"] = (mr == args.concurrency)

    metrics = {
        "experiment_id": args.experiment_id, "schema_version": SCHEMA_VERSION,
        "client_version": CLIENT_VERSION,
        "mode": args.mode, "fixture_name": args.fixture_name,
        "fixture_sha256": args.fixture_sha,
        "concurrency": args.concurrency, "max_tokens": args.max_tokens,
        "requested_output_tokens": args.max_tokens,
        "requests_total": len(per_req), "requests_ok": len(ok_reqs),
        "http_errors": len(per_req) - len(ok_reqs),
        "count_mismatch_samples": sum(1 for r in raw if r["outcome"].get("count_mismatch")),
        "early_stop_samples": sum(1 for r in ok_reqs if r["early_stop"]),
        "sampler_stats": {"metrics_endpoint": msamp.stats(), "nvml": nsamp.stats()},
        "per_request": per_req,
        "percentiles": compute_percentiles_if_enough(per_req),
        "aggregate": agg,
    }

    # 落盘（run 结束后一次性写）
    with open(os.path.join(args.out_dir, "raw-events.jsonl"), "w") as f:
        for r in raw:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1, ensure_ascii=False)
    with open(os.path.join(args.out_dir, "sampler-metrics.jsonl"), "w") as f:
        for s in msamp.samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out_dir, "nvml-samples.jsonl"), "w") as f:
        for s in nsamp.samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    hs = {}
    for p in ("host-snapshot.json", "env-lock.json"):
        fp = os.path.join(os.path.dirname(args.host_snapshot), p)
        if os.path.exists(fp):
            hs[p] = sha256_file(fp)
    harness_files = {}
    for fn in HARNESS_FILES:
        fp = os.path.join(HERE, fn)
        if os.path.exists(fp):
            harness_files[fn] = sha256_file(fp)
    initial_temps = [c["temp_c"] for c in nsamp.samples[:max(1, args.concurrency)]]
    # 卡身份全集：logical_index + uuid + pci_bdf（三方齐全才可归档 valid）
    by_uuid = {c["uuid"]: c for c in nvml_bind.snapshot_gpus()}
    cards_manifest = [
        {"logical_index": by_uuid.get(u, {}).get("logical_index"), "uuid": u,
         "pci_bdf": by_uuid.get(u, {}).get("pci_bdf"),
         "role": f"tp_rank_{rank}",
         "power_limit_w": by_uuid.get(u, {}).get("power_limit_w")}
        for rank, u in enumerate(uuids or [])]
    manifest = {
        "experiment_id": args.experiment_id,
        "status": "VALID_PASS",  # 占位；classify.py 依 Gate 重判
        "evidence_class": "staging",
        "classification_reason": None,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "harness_git_sha": git_sha(),
        "harness_files_sha256": harness_files,
        "host_snapshot_sha256": hs.get("host-snapshot.json"),
        "env_lock_sha256": hs.get("env-lock.json"),
        "gpu": {
            "cards": cards_manifest,
            "power_limit_w": (nsamp.samples[0]["power_limit_w"] if nsamp.samples else None),
            "initial_temp_c": initial_temps,
        },
        "server": {"port": args.port, "pid": args.server_pid, "pgid": args.server_pgid,
                   "tp": args.tp, "max_num_seqs": args.ms,
                   "launch_cmd_file": "launch-cmd.txt",
                   "cache_root": args.cache_root},
        "fixture": {"name": args.fixture_name, "sha256": args.fixture_sha,
                    "requested_output_tokens": args.max_tokens,
                    "actual_input_tokens": (raw[0]["fixture"]["actual_input_tokens"]
                                            if raw else None)},
        "recipe": {"runtime": "vllm-0.28.0", "kv_profile": "kvarn_k4v2_g128",
                   "quant": "W4A16-autoround-g128", "spec": "dflash2-k7",
                   "nbt": 2048, "cudagraph": "cg8-custom-ops"},
        "timing": {"start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_batch_launch / 1e9)),
                   "end_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_batch_end / 1e9)),
                   "duration_s": round(batch_wall_s, 3)},
        "files": {"raw_events": "raw-events.jsonl", "metrics": "metrics.json",
                  "sampler_metrics": "sampler-metrics.jsonl", "nvml": "nvml-samples.jsonl"},
        "client_version": CLIENT_VERSION,
    }
    with open(os.path.join(args.out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)

    summary = {
        "experiment_id": args.experiment_id, "ok": metrics["requests_ok"],
        "total": metrics["requests_total"],
        "e2e_output_tok_s": [r["e2e_output_tok_s"] for r in perf_reqs],
        "client_observed_decode_tok_s": [r["client_observed_decode_tok_s"] for r in perf_reqs],
        "ttft_s": [r["ttft_s"] for r in perf_reqs],
        "aggregate_output_tok_s": agg.get("aggregate_output_tok_s"),
        "max_running": mr, "early_stops": metrics["early_stop_samples"],
        "count_mismatch": metrics["count_mismatch_samples"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    # 退出码：0=run 完成；2=完成但有效性检查失败；3=全部失败
    valid = (metrics["requests_ok"] == metrics["requests_total"]
             and metrics["count_mismatch_samples"] == 0
             and msamp.exit_code == 0 and nsamp.exit_code == 0
             and (args.mode != "fixed-output" or metrics["early_stop_samples"] == 0))
    return 0 if valid else (3 if metrics["requests_ok"] == 0 else 2)


if __name__ == "__main__":
    sys.exit(main())
