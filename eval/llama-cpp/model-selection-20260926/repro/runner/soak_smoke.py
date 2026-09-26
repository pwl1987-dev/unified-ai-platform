"""soak_smoke.py — 30-min sustained smoke for the frozen BENCHMARK-RUNTIME with CONTROL-PROD model.
Mixed load loop: 1K chat, 32K chat, strict JSON, tool call, periodic 128K; monitors VRAM/RSS drift.
Usage: uv run python soak_smoke.py <image> <gpu> [minutes] [port]
"""
from __future__ import annotations
import json, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

PROD_CMD = ("-m /prodmodels/Qwen3.8-27B-coding-v1.1-iq4xs.gguf --host 0.0.0.0 --port 8080 "
            "-c 262144 -np 1 -ngl 999 --cache-type-k q4_0 --cache-type-v q4_0 "
            "--spec-draft-type-k q8_0 --spec-draft-type-v q8_0 -fa on --cache-reuse 2048 "
            "--jinja -a soak --metrics --spec-type draft-dflash "
            "-md /prodmodels/Qwen3.8-27B-DFlash2-Q4_K_M.gguf --spec-draft-n-max 7")


def container_rss_mib(name: str) -> float:
    out = lab.sh(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name]).stdout.strip()
    try:
        return float(out.split("/")[0].strip().rstrip("MiBGiB ").strip()) if "MiB" in out else float(out.split("/")[0].strip().rstrip("GiB")) * 1024
    except Exception:
        return -1


def main():
    """Usage: soak_smoke.py <image> <gpu_csv> [minutes] [port] [model_path] [ctx] [extra_flags]
    Defaults keep the CONTROL-PROD model; passing model_path switches to a candidate."""
    image = sys.argv[1]
    gpu = sys.argv[2] if len(sys.argv) > 2 else "2"
    minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 18101
    model = sys.argv[5] if len(sys.argv) > 5 else "/prodmodels/Qwen3.8-27B-coding-v1.1-iq4xs.gguf"
    ctx = int(sys.argv[6]) if len(sys.argv) > 6 else 262144
    extra = sys.argv[7] if len(sys.argv) > 7 else ("--spec-type draft-dflash -md /prodmodels/Qwen3.8-27B-DFlash2-Q4_K_M.gguf "
             "--spec-draft-n-max 7 --spec-draft-type-k q8_0 --spec-draft-type-v q8_0 --cache-reuse 2048")
    suffix = "-cand" if "prodmodels" not in model else ""
    cname = f"lab-soak{suffix}"
    cmd = (f"-m {model} --host 0.0.0.0 --port 8080 -c {ctx} -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a soak --metrics {extra}")
    # reuse an already-healthy server on this port if present (avoids restart flakiness)
    try:
        if httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).status_code != 200:
            raise Exception("boot")
    except Exception:
        lab.server_up(cname, image, port, gpu, cmd)
    rec = {"image": image, "gpu": gpu, "minutes": minutes, "samples": [], "errors": 0, "iters": 0}
    filler, _ = lab.make_filler(131072, port)
    tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object",
             "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
    t_end = time.time() + minutes * 60
    i = 0
    while time.time() < t_end:
        i += 1
        try:
            if i % 5 == 0:
                sub, n = lab.cut_to_tokens(filler, port, 131072)
                r = lab.chat(port, [{"role": "user", "content": sub + "\n\n一句话总结上文。"}], max_tokens=200, temperature=0.0, seed=42)
            elif i % 3 == 0:
                r = lab.chat(port, [{"role": "user", "content": '返回严格 JSON：{"ok":true,"n":7}'}], max_tokens=100,
                             temperature=0.0, seed=1, extra={"response_format": {"type": "json_object"}})
            elif i % 3 == 1:
                msg = lab.chat_nonstream(port, [{"role": "user", "content": "上海天气？"}],
                                         extra={"tools": tools, "tool_choice": "auto"}, max_tokens=200)
                r = {"wall_s": 0, "ttft_s": None}
            else:
                r = lab.chat(port, [{"role": "user", "content": "用三句话解释 docker 网络桥接模式。"}], max_tokens=300, temperature=0.0, seed=7)
            rec["iters"] = i
            rec["samples"].append({"i": i, "t": round(time.time() % 86400), "wall_s": r.get("wall_s"),
                                   "vram": lab.vram_mib(gpu)["vram_used_mib"], "rss_mib": container_rss_mib(cname)})
            print(f"  iter{i} wall={r.get('wall_s')} vram={rec['samples'][-1]['vram']} rss={rec['samples'][-1]['rss_mib']}", flush=True)
        except Exception as e:
            rec["errors"] += 1
            rec["samples"].append({"i": i, "error": str(e)[:150]})
            print(f"  iter{i} ERROR {str(e)[:100]}", flush=True)
        time.sleep(4)
    rec["tps_total"] = lab.parse_tps(cname)
    rec["final_vram"] = lab.vram_mib(gpu)
    lab.write_json(lab.EVID / "runs" / "runtime-ab" / f"soak-smoke{suffix}.json", rec)
    lab.server_down(cname)
    print(f"SOAK DONE iters={rec['iters']} errors={rec['errors']}")


if __name__ == "__main__":
    main()
