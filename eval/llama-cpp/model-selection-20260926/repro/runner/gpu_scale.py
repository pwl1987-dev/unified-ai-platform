"""gpu_scale.py — 1 vs 2 (vs 4) GPU scaling for a model: max ctx fit, ladder TPS, VRAM per GPU.
Usage: uv run python gpu_scale.py <image> <gpu_csv e.g. 2 or 2,4> <model_path> <model_key> <ctx> [port] [tensor_split]
Output: evidence runs/gpu/<model_key>-g<ngpu>.json
"""
from __future__ import annotations
import json, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab


def vram_all(gpu_csv: str) -> list:
    return {g: lab.vram_mib(g)["vram_used_mib"] for g in gpu_csv.split(",")}


def main():
    image, gpu_csv, model_path, key, ctx = sys.argv[1:6]
    ctx = int(ctx)
    port = int(sys.argv[6]) if len(sys.argv) > 6 else 18231
    tsplit = sys.argv[7] if len(sys.argv) > 7 else ("--tensor-split 1,1" if "," in gpu_csv else "")
    ngpu = len(gpu_csv.split(","))
    cname = f"gpu-{key}-g{ngpu}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c {ctx} -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a gpu "
           f"-b 1024 -ub 1024 --metrics {tsplit}")
    rec = {"model": key, "gpus": gpu_csv, "ctx": ctx, "tensor_split": tsplit}
    try:
        rec["health_s"] = round(lab.server_up(cname, image, port, gpu_csv, cmd), 1)
        rec["vram_after_load"] = vram_all(gpu_csv)
        filler, _ = lab.make_filler(ctx, port)
        rec["ladder"] = []
        for target in [s for s in (32768, 131072, 262144) if s <= ctx]:
            sub, n = lab.cut_to_tokens(filler, port, target - 4096)
            lab._LASTLOG_POS[cname] = len(lab.docker_logs(cname))
            r = lab.chat(port, [{"role": "user", "content": sub + "\n\n一句话总结。"}],
                         max_tokens=160, temperature=0.0, seed=42)
            tps = lab.parse_tps(cname)
            rec["ladder"].append({"ctx": target, "n": n, "ttft_s": r["ttft_s"], "wall_s": r["wall_s"],
                                  "ptps": tps["prompt_tps"][-1] if tps["prompt_tps"] else None,
                                  "dtps": tps["decode_tps"][-1] if tps["decode_tps"] else None})
            print(f"  ctx{target//1024}K ttft={r['ttft_s']} ptps={rec['ladder'][-1]['ptps']} dtps={rec['ladder'][-1]['dtps']}", flush=True)
        rec["vram_peak"] = vram_all(gpu_csv)
        import re
        logs = lab.docker_logs(cname)
        rec["offload_line"] = (re.findall(r"offloaded \d+/64", logs) or [None])[0]
        (lab.EVID / "runs" / "gpu").mkdir(parents=True, exist_ok=True)
        lab.write_json(lab.EVID / "runs" / "gpu" / f"{key}-g{ngpu}.json", rec)
    except Exception as e:
        rec["error"] = str(e)[:300]
        lab.write_json(lab.EVID / "runs" / "gpu" / f"{key}-g{ngpu}.json", rec)
    finally:
        lab.server_down(cname)
    print(json.dumps(rec, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
