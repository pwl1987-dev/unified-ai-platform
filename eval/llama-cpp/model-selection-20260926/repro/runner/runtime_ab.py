"""runtime_ab.py — RUNTIME-CURRENT vs CUDA13-official vs CUDA12-official A/B.

Fixed model = CONTROL-PROD model + draft (exact prod args). Same GPU (default 2).
Phases per runtime:
  1) 5x cold start (container start -> health 200), VRAM after load
  2) warm context ladder 1K/32K/128K/256K: client TTFT/wall + server-side TPS
  3) strict JSON + tool-call smoke
  4) GPU backend facts from logs (cuda init, compute cap, offload, FA)
Output: evidence runs/runtime-ab/<runtime>.json
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

COLDS = int(os.environ.get("COLDS", "5"))

EVID = lab.EVID
RUNTIMES = {
    "current-cuda12.4-b10715": {
        "image": "llama-server:cuda12.4-b10715",
        "digest": "sha256:cc0782dc7b595e34ca2611729d7d23e47db6aa3d09aff4f9a8ddc3fd45f751fa",
        "cuda_runtime": "12.4.1 (nvidia/cuda:12.4.1-runtime-ubuntu22.04)",
    },
    "official-cuda12": {
        "image": "ghcr.io/ggml-org/llama.cpp:server-cuda",
        "digest": None,  # filled at runtime from docker inspect
        "cuda_runtime": None,
    },
    "local-cuda13-sm89": {
        "image": "local/llama.cpp:master-171e8846b4af-cuda13-sm89",
        "digest": None,
        "cuda_runtime": "13.0.1 (local build, CMAKE_CUDA_ARCHITECTURES=89)",
    },
}
# official-cuda13 (server-cuda13 = CUDA 13.4.1, requires driver cuda>=13.4; earliest cuda13 tag
# b7588 = CUDA 13.1.0 requires >=13.1): NOT runnable on host driver 580.173.02 (capability 13.0).
# Recorded in runtime-matrix.json as hard-incompatible; not executed.
PROD_CMD = ("-m /prodmodels/Qwen3.8-27B-coding-v1.1-iq4xs.gguf --host 0.0.0.0 --port 8080 "
            "-c 262144 -np 1 -ngl 999 --cache-type-k q4_0 --cache-type-v q4_0 "
            "--spec-draft-type-k q8_0 --spec-draft-type-v q8_0 -fa on --cache-reuse 2048 "
            "--jinja -a test --metrics --spec-type draft-dflash "
            "-md /prodmodels/Qwen3.8-27B-DFlash2-Q4_K_M.gguf --spec-draft-n-max 7")

LADDER = [1024, 32768, 131072, 262144]
GEN_TOKENS = 256


def image_digest(image: str) -> str:
    out = lab.sh(["docker", "image", "inspect", image, "--format", "{{join .RepoDigests \" \"}} {{.Id}}"]).stdout.strip()
    return out


def main(gpu: str = "2", only: str | None = None) -> None:
    outdir = EVID / "runs" / "runtime-ab"
    outdir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for i, (rt_name, rt) in enumerate(RUNTIMES.items()):
        if only and rt_name != only:
            continue
        port = 18101 + i
        cname = f"lab-rt{i+1}"
        rt["digest"] = image_digest(rt["image"])
        rec: dict = {"runtime": rt_name, **rt, "gpu": gpu, "cmd": PROD_CMD, "cold_starts": [],
                     "ladder": [], "smoke": {}, "log_facts": {}}
        print(f"=== {rt_name} on GPU{gpu} port {port}", flush=True)
        # -- 1) cold starts --
        for cs in range(COLDS):
            lab.server_down(cname)
            t_health = lab.server_up(cname, rt["image"], port, gpu, PROD_CMD)
            time.sleep(2)
            loadinfo = lab.load_time_from_logs(cname)
            vram = lab.vram_mib(gpu)
            rec["cold_starts"].append({"cycle": cs + 1, "health_after_s": round(t_health, 1),
                                       "model_load_ms": loadinfo.get("model_load_ms"), "vram_after_load": vram})
            print(f"  cold#{cs+1}: health {t_health:.0f}s load {loadinfo.get('model_load_ms')}ms vram {vram['vram_used_mib']}MiB", flush=True)
        # -- 2) warm ladder (server still up from last cold start; first request warms) --
        filler, _ = lab.make_filler(max(LADDER), port)
        for target in LADDER:
            sub, n = lab.cut_to_tokens(filler, port, target)
            msgs = [{"role": "system", "content": "你是严谨的助手。"}, {"role": "user", "content": sub + "\n\n请用一句话总结上文的主旨，并给出你看到的最大编号数字。"}]
            lab._LASTLOG_POS[cname] = len(lab.docker_logs(cname))
            r = lab.chat(port, msgs, max_tokens=GEN_TOKENS, temperature=0.0, seed=42)
            tps = lab.parse_tps(cname)
            vram = lab.vram_mib(gpu)
            entry = {"ctx_target": target, "prompt_tokens": n, **{k: r[k] for k in ("ttft_s", "wall_s", "usage", "sha_output")},
                     "server": tps, "vram_peak": vram, "answer_head": r["text"][:120]}
            rec["ladder"].append(entry)
            pt = tps["prompt_tps"][-1] if tps["prompt_tps"] else None
            dt = tps["decode_tps"][-1] if tps["decode_tps"] else None
            print(f"  ctx {target//1024}K: prompt_toks={n} ttft={r['ttft_s']}s wall={r['wall_s']}s ptps={pt} dtps={dt} vram={vram['vram_used_mib']}MiB", flush=True)
        # -- 3) JSON / tool smoke --
        rj = lab.chat(port, [{"role": "user", "content": "输出严格 JSON：{\"ok\":true,\"n\":42,\"tags\":[\"a\",\"b\"]}，不要多余文字。"}],
                      max_tokens=200, temperature=0.0, seed=1, extra={"response_format": {"type": "json_object"}})
        try:
            parsed = json.loads(rj["text"].strip().strip("`"))
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            json_ok = True
        except Exception:
            json_ok = False
        tools = [{"type": "function", "function": {"name": "get_weather", "description": "query weather",
                                                   "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
        tool_msg = {}
        try:
            tool_msg = lab.chat_nonstream(port, [{"role": "user", "content": "北京今天天气如何？调用工具查询。"}],
                                          extra={"tools": tools, "tool_choice": "auto"})
        except Exception as e:
            tool_msg = {"error": str(e)}
        rec["smoke"] = {"strict_json_valid": json_ok, "json_text_head": rj["text"][:150],
                        "tool_call_message": tool_msg}
        # -- 4) log facts --
        logs = lab.docker_logs(cname)
        facts = {}
        for key, pat in {
            "ggml_cuda_init": r"ggml_cuda_init:.*",
            "device0": r"Device 0:.*",
            "offload": r"offloading \d+ repeating layers.*",
            "flash_attn": r"flash_attn.*",
            "kv_quant": r"kv cache quantization.*",
            "spec": r"speculative.*",
        }.items():
            m = __import__("re").search(pat, logs)
            facts[key] = m.group(0)[:200] if m else None
        (outdir / f"{cname}-logs.txt").write_text(logs[-200000:])
        rec["log_facts"] = facts
        results[rt_name] = rec
        lab.write_json(outdir / f"{rt_name}.json", rec)
        lab.server_down(cname)
        print(f"=== {rt_name} done -> {outdir/(rt_name+'.json')}", flush=True)
    lab.write_json(outdir / "runtime-ab-summary.json", results)


if __name__ == "__main__":
    gpu = sys.argv[1] if len(sys.argv) > 1 else "2"
    only = sys.argv[2] if len(sys.argv) > 2 else None
    main(gpu, only)
