"""soak_plain.py — minimal sustained-load soak against an ALREADY-RUNNING server.
Usage: uv run python soak_plain.py <port> <minutes> <gpu_csv> <key>
Writes evidence runs/soak/<key>-soak.json. No container management at all.
"""
from __future__ import annotations
import json, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

port = int(sys.argv[1])
minutes = int(sys.argv[2])
gpu = sys.argv[3]
key = sys.argv[4]

filler = None
rec = {"key": key, "port": port, "samples": [], "errors": 0, "iters": 0}
tools = [{"type": "function", "function": {"name": "get_weather",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
t_end = time.time() + minutes * 60
i = 0
while time.time() < t_end:
    i += 1
    try:
        if i % 5 == 0:
            sub, n = lab.cut_to_tokens(filler, port, 131072 - 4096) if filler else ("", 0)
            if not sub:
                filler, _ = lab.make_filler(131072 - 4096, port)
                sub, n = lab.cut_to_tokens(filler, port, 131072 - 4096)
            r = lab.chat(port, [{"role": "user", "content": sub + "\n\n一句话总结上文。"}], max_tokens=200, temperature=0.0, seed=42)
        elif i % 3 == 0:
            r = lab.chat(port, [{"role": "user", "content": '返回严格 JSON：{"ok":true,"n":7}'}], max_tokens=100,
                         temperature=0.0, seed=1, extra={"response_format": {"type": "json_object"}})
        elif i % 3 == 1:
            lab.chat_nonstream(port, [{"role": "user", "content": "上海天气？"}],
                               extra={"tools": tools, "tool_choice": "auto"}, max_tokens=200)
            r = {"wall_s": 0.5, "ttft_s": None}
        else:
            r = lab.chat(port, [{"role": "user", "content": "用三句话解释 docker 网络桥接模式。"}], max_tokens=300, temperature=0.0, seed=7)
        rec["iters"] = i
        rec["samples"].append({"i": i, "wall_s": r.get("wall_s"),
                               "vram": lab.vram_mib(gpu)["vram_used_mib"]})
        if i % 20 == 0:
            print(f"  iter{i} wall={r.get('wall_s')} vram={rec['samples'][-1]['vram']}", flush=True)
    except Exception as e:
        rec["errors"] += 1
        rec["samples"].append({"i": i, "error": str(e)[:150]})
        print(f"  iter{i} ERROR {str(e)[:100]}", flush=True)
    time.sleep(4)
rec["final_vram"] = lab.vram_mib(gpu)
(lab.EVID / "runs" / "soak").mkdir(parents=True, exist_ok=True)
lab.write_json(lab.EVID / "runs" / "soak" / f"{key}-soak.json", rec)
print(f"SOAK {key} DONE iters={rec['iters']} errors={rec['errors']}")
