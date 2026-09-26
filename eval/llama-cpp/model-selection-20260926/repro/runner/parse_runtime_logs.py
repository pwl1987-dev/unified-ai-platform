"""parse_runtime_logs.py — backfill server-side TPS into runtime-ab JSONs from saved logs .txt.

Usage: uv run python parse_runtime_logs.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

EVID = Path("/data/tasks/qwen-model-lab/benchmarks/llama-cpp/model-selection-2026-09/runs/runtime-ab")

PT = re.compile(r"prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s+tokens\s*\(.*?([\d.]+)\s+tokens per second\)")
ET = re.compile(r"\|\s+eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s+tokens\s*\(.*?([\d.]+)\s+tokens per second\)")


def main():
    for jf in sorted(EVID.glob("*.json")):
        if jf.name == "runtime-ab-summary.json":
            continue
        data = json.loads(jf.read_text())
        cname = "lab-" + {"current-cuda12.4-b10715": "rt1", "official-cuda12": "rt2", "local-cuda13-sm89": "rt3"}.get(data["runtime"], "rtX")
        logs_file = EVID / f"{cname}-logs.txt"
        if not logs_file.exists():
            continue
        logs = logs_file.read_text(errors="replace")
        pt = PT.findall(logs)
        et = ET.findall(logs)
        if not pt and not et:
            continue
        # ladder steps are the LAST 4 prompt-eval entries (1K,32K,128K,256K after cold starts)
        data["server_tps_backfill"] = {
            "prompt": [{"ms": float(a), "tokens": int(b), "tps": float(c)} for a, b, c in pt],
            "decode": [{"ms": float(a), "tokens": int(b), "tps": float(c)} for a, b, c in et],
        }
        jf.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(jf.name, "prompt_entries", len(pt), "decode_entries", len(et))


if __name__ == "__main__":
    main()
