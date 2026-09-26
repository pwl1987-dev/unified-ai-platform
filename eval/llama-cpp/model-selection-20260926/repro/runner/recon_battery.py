"""recon_battery.py — §14 small reconciliation battery for ISTA (same evaluators as the main
campaign, ONLY fix: max_tokens 3072->8192 so thinking can terminate).

3 coding + 3 longcode(real-repo) + 3 structured + 3 agent-tool + needle 32K/128K/256K.
Usage: uv run python recon_battery.py <port> <gpu> <out_key>
"""
from __future__ import annotations
import json, re, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab
import coding as CODING
import structured as STRUCT
import agent as AGENT

BUDGET = 8192  # the single harness fix; everything else identical to main campaign
EVID = lab.EVID / "reconciliation"


def chat_ok(port, messages, extra=None):
    r = lab.chat(port, messages, max_tokens=BUDGET, temperature=0.0, seed=42, extra=extra)
    return r


def main():
    port = int(sys.argv[1])
    gpu = sys.argv[2]
    key = sys.argv[3]
    rec = {"key": key, "budget": BUDGET, "note": "same evaluators as main campaign; only max_tokens raised 3072->8192",
           "coding": [], "longcode": [], "structured": [], "agent": [], "needle": []}
    # 3 coding (exact tasks + exec verification)
    for t in [CODING.task_python_merge, CODING.task_python_lru, CODING.task_python_bugfix]:
        # monkeypatch budget inside coding tasks: they hardcode max_tokens; wrap via lab.chat override
        orig_chat = lab.chat
        def chat_big(port_, messages, max_tokens=512, **kw):
            return orig_chat(port_, messages, max_tokens=BUDGET, **kw)
        lab.chat = chat_big
        CODING.lab.chat = chat_big
        try:
            r = t(port)
        finally:
            lab.chat = orig_chat
            CODING.lab.chat = orig_chat
        rec["coding"].append(r)
        print("  coding", r["id"], "pass", r["pass"], flush=True)
    # 3 longcode real-repo (same questions + grep ground truth), trimmed to the live server ctx
    from longcode import real_repo_corpus, REAL_TASKS
    import httpx as _hx
    m = _hx.get(f"http://127.0.0.1:{port}/v1/models", timeout=30).json()
    srv_ctx = min(131072, int(m["data"][0].get("context_length") or m["data"][0].get("meta", {}).get("n_ctx") or 65536))
    corpus = real_repo_corpus()
    n = lab.tokenize(port, corpus)
    while n > srv_ctx - 4096 and len(corpus) > 10000:
        corpus = corpus[: int(len(corpus) * (srv_ctx - 8192) / n)]
        n = lab.tokenize(port, corpus)
    for t in REAL_TASKS[:3]:
        r = lab.chat(port, [{"role": "user", "content": corpus + "\n\n" + t["q"]}], max_tokens=BUDGET,
                     temperature=0.0, seed=42)
        ok = 1 if all(g.lower() in r["text"].lower() for g in t["gt"]) else 0
        rec["longcode"].append({"q": t["q"][:40], "pass": ok, "text_head": r["text"][:120], "wall_s": r["wall_s"]})
        print("  longcode", t["q"][:20], "pass", ok, flush=True)
    # 3 structured (same cases + jsonschema)
    for cid in ["strict_flat", "nested_deep", "enum_array_nullable"]:
        case = next(c for c in STRUCT.CASES if c["id"] == cid)
        extra = {"response_format": {"type": "json_object"}} if case.get("json_mode") else None
        r = lab.chat(port, [{"role": "user", "content": case["prompt"]}], max_tokens=BUDGET,
                     temperature=0.0, seed=42, extra=extra)
        import jsonschema
        ok, err = 0, ""
        try:
            text = r["text"].strip()
            if text.startswith("```"):
                m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
                if m:
                    text = m.group(1)
            jsonschema.validate(json.loads(text), case["schema"])
            ok = 1
        except Exception as e:
            err = str(e)[:120]
        rec["structured"].append({"id": cid, "pass": ok, "err": err, "text_head": r["text"][:100]})
        print("  structured", cid, "pass", ok, flush=True)
    # 3 agent scenarios (same simulated env)
    for s in [AGENT.sc_single, AGENT.sc_multi, AGENT.sc_dependent]:
        r = s(port)
        rec["agent"].append(r)
        print("  agent", r.get("id", "?"), "pass", r.get("pass"), flush=True)
    # needles 32/128/256K (same needles/depth/mode as battery)
    from needle import build_doc, MARGIN
    filler, _ = lab.make_filler(262144 - MARGIN, port)
    for ctx in (32768, 131072, 262144):
        for mode, depth in [("single", 0.5), ("multi4", 0.5)]:
            msgs, expected, np_ = build_doc(filler, port, ctx, mode, depth)
            r = lab.chat(port, msgs, max_tokens=BUDGET, temperature=0.0, seed=42)
            hits = [e for e in expected if e in r["text"]]
            rec["needle"].append({"ctx": ctx, "mode": mode, "pass": 1 if len(hits) == len(expected) else 0,
                                  "hits": f"{len(hits)}/{len(expected)}", "wall_s": r["wall_s"]})
            print(f"  needle {ctx//1024}K {mode}: {len(hits)}/{len(expected)}", flush=True)
    rec["score"] = {"coding": sum(t["pass"] for t in rec["coding"]),
                    "longcode": sum(t["pass"] for t in rec["longcode"]),
                    "structured": sum(t["pass"] for t in rec["structured"]),
                    "agent": sum(t.get("pass", 0) for t in rec["agent"]),
                    "needle": sum(t["pass"] for t in rec["needle"]), "needle_n": len(rec["needle"])}
    lab.write_json(EVID / f"{key}-battery.json", rec)
    print(json.dumps(rec["score"]))


if __name__ == "__main__":
    main()
