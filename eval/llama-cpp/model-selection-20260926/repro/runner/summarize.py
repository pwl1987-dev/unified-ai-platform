"""summarize.py — aggregate all evidence into summary.json + pareto.json.
Usage: uv run python summarize.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

EVID = Path("/data/tasks/qwen-model-lab/benchmarks/llama-cpp/model-selection-2026-09/runs")
R = EVID.parent

MODELS = {
    "A-ista-gsq-iq3s-mtp": "ISTA Qwen3.8 GSQ-RCO IQ3_S-mtp (base control)",
    "B-swift15-gsq-iq3s-mtp": "Swift1.5 GSQ-RCO IQ3_S-mtp (longctx candidate)",
    "C-swift15-q5km": "Swift1.5 Q5_K_M (quality candidate)",
    "D-swift10-q4km": "Swift1.0 Q4_K_M (regression control)",
}


def jload(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def stage1_axes():
    out = {}
    for k in MODELS:
        d = jload(EVID / "stage1" / f"{k}.json")
        if not d or "probes" not in d:
            continue
        p = d["probes"]
        out[k] = {
            "stage1_pass": sum(1 for v in p.values() if v.get("pass")) / max(len(p), 1),
            "zh_default_ok": p.get("zh", {}).get("pass"),
            "thinking_chars_zh": p.get("zh", {}).get("reasoning_chars"),
            "vram_1gpu_64k_mib": d.get("vram_after_load", {}).get("vram_used_mib"),
        }
    return out


def suite_axes():
    out = {}
    for k in MODELS:
        rec = {}
        nd = jload(EVID / "longctx" / f"{k}-needle.json")
        if nd:
            rec["needle_summary"] = nd["summary"]
        lc = jload(EVID / "long-code" / f"{k}.json")
        if lc:
            rec["longcode"] = {"real": sum(t["pass"] for t in lc["tasks"] if t["part"] == "real-repo"),
                               "real_n": sum(1 for t in lc["tasks"] if t["part"] == "real-repo"),
                               "synth": sum(t["pass"] for t in lc["tasks"] if t["part"] == "synth-locate"),
                               "synth_n": sum(1 for t in lc["tasks"] if t["part"] == "synth-locate"),
                               "patch": lc.get("patch", {}).get("pass")}
        cd = jload(EVID / "coding" / f"{k}.json")
        if cd:
            rec["coding"] = {"score": cd["score"], "n": len(cd["tasks"])}
        st = jload(EVID / "structured-output" / f"{k}.json")
        if st:
            rec["structured"] = st["score"]
        ag = jload(EVID / "agent" / f"{k}.json")
        if ag:
            rec["agent"] = {"score": ag["score"], "n": len(ag["scenarios"])}
        wr = jload(EVID / "writing" / f"{k}.json")
        if wr:
            rec["writing"] = {"score": wr["score"], "n": len(wr["tasks"])}
        opt = jload(EVID / "opt" / f"{k}.json")
        if opt:
            rec["opt_configs"] = {c["id"]: {"corr": c.get("correctness"),
                                            "ladder": c.get("ladder"),
                                            "vram": c.get("vram_after_load", {}).get("vram_used_mib"),
                                            "error": c.get("error")} for c in opt["configs"]}
        conc = jload(EVID / "concurrency" / f"{k}.json")
        if conc:
            rec["concurrency"] = conc["waves"]
        for g in (1, 2, 4):
            gsc = jload(EVID / "gpu" / f"{k}-g{g}.json")
            if gsc:
                rec[f"gpu{g}"] = {"ladder": gsc.get("ladder"), "vram": gsc.get("vram_after_load"),
                                  "error": gsc.get("error")}
        vis = {}
        for mode in ("cpu", "gpu"):
            v = jload(EVID / "vision" / f"{k}-{mode}.json")
            if v:
                vis[mode] = {"score": sum(c["pass"] for c in v["cases"]), "n": len(v["cases"]),
                             "vram": v["vram_after_load"]["vram_used_mib"],
                             "mean_ttft": round(sum(c.get("ttft_s") or 0 for c in v["cases"]) / max(len(v["cases"]), 1), 2)}
        if vis:
            rec["vision"] = vis
        out[k] = rec
    return out


def main():
    summary = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "stage1": stage1_axes(),
        "suites": suite_axes(),
    }
    (R / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    # pareto: hard gates first (128K usable + zh ok + restart), then frontier on axes
    pareto = {"hard_gates": {}, "frontier_notes": []}
    s1 = summary["stage1"]
    su = summary["suites"]
    for k in MODELS:
        gates = {}
        gates["128K"] = (su.get(k, {}).get("needle_summary", {}).get("131072", {}).get("pass_rate", None))
        gates["256K"] = (su.get(k, {}).get("needle_summary", {}).get("262144", {}).get("pass_rate", None))
        gates["zh_default"] = s1.get(k, {}).get("zh_default_ok")
        gates["json_tool_stage1"] = None
        pareto["hard_gates"][k] = gates
    (R / "pareto.json").write_text(json.dumps(pareto, ensure_ascii=False, indent=1))
    print(json.dumps(summary["stage1"], ensure_ascii=False, indent=1))
    print("summary.json / pareto.json written")


if __name__ == "__main__":
    main()
