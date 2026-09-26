"""needle.py — long-context needle battery for top candidates (machine-scored).

Depths 10/25/50/75/90/98%; modes: single / multi4 / distractor; ctx ladder configurable.
Deterministic filler; needles unique alphanumeric facts; scoring = exact substring.
Usage: uv run python needle.py <image> <gpu> <model_path> <model_key> <ctx_csv> <kv_extra>
Output: evidence runs/longctx/<model_key>-needle.json
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

NEEDLES = [
    "【内部备忘 A】本次评审会议的临时密码是 X7K9-42ZQ，会后立即作废。",
    "【内部备忘 B】备用发电机的燃油编号为 FD-88123，仅行政岗可领取。",
    "【内部备忘 C】3 号机柜的维护窗口是每周四 03:15-04:00，值班表贴在门后。",
    "【内部备忘 D】食堂临时供应商的结算账号末四位是 7741，对账用。",
]
DISTRACTOR = "【内部备忘 E】旧的评审会议密码是 X7K9-42ZP（已作废，注意与现行密码区分）。"
# server-side (template-applied) token count runs ~2K above client /tokenize; keep 4K margin
MARGIN = 4096
DEPTH_GRID = {32768: [0.25, 0.75], 131072: [0.10, 0.25, 0.50, 0.75, 0.90, 0.98], 262144: [0.10, 0.50, 0.98]}


def depths_for(ctx: int) -> list:
    if ctx in DEPTH_GRID:
        return DEPTH_GRID[ctx]
    return [0.10, 0.50, 0.98]


def build_doc(filler: str, port: int, ctx_target: int, mode: str, depth: float) -> tuple[list, list, int]:
    sub, n = lab.cut_to_tokens(filler, port, ctx_target - MARGIN)
    def insert(s: str, frac: float, text: str) -> str:
        pos = int(len(s) * frac)
        return s[:pos] + f"\n{text}\n" + s[pos:]
    expected = []
    if mode == "single":
        sub = insert(sub, depth, NEEDLES[0])
        expected = ["X7K9-42ZQ"]
        q = "上文中的会议临时密码是什么？只输出密码本身。"
    elif mode == "multi4":
        ds = [0.1, 0.35, 0.6, 0.9] if abs(depth - 0.5) < 0.01 else [depth, 0.3, 0.55, 0.8]
        for nd, d in zip(NEEDLES, ds):
            sub = insert(sub, d, nd)
        expected = ["X7K9-42ZQ", "FD-88123", "03:15-04:00", "7741"]
        q = ("上文给出了四条内部备忘（会议密码/发电机燃油编号/3号机柜维护窗口/食堂结算账号末四位）。"
             "逐条输出：密码、燃油编号、维护窗口时间段、账号末四位。一行一条。")
    else:  # distractor
        sub = insert(sub, depth, NEEDLES[0])
        sub = insert(sub, min(depth + 0.03, 0.99), DISTRACTOR)
        expected = ["X7K9-42Q" if False else "X7K9-42ZQ"]
        q = "上文中的现行会议临时密码是什么？只输出密码本身（注意区分已作废的旧密码）。"
    return [{"role": "user", "content": sub + f"\n\n{q}"}], expected, n


def run(image: str, gpu: str, model_path: str, key: str, ctxs: list[int], extra_kv: str, port: int) -> dict:
    cname = f"needle-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c {max(ctxs)} -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a needle "
           f"-b 1024 -ub 1024 --metrics {extra_kv}")
    rec = {"model": key, "path": model_path, "image": image, "gpu": gpu, "ctxs": ctxs, "cases": []}
    t0 = time.time()
    lab.server_up(cname, image, port, gpu, cmd)
    rec["vram_after_load"] = lab.vram_mib(gpu)
    filler, _ = lab.make_filler(max(ctxs) - MARGIN, port)
    for ctx in ctxs:
        for mode in ["single", "multi4", "distractor"]:
            for depth in depths_for(ctx):
                msgs, expected, n = build_doc(filler, port, ctx, mode, depth)
                try:
                    r = lab.chat(port, msgs, max_tokens=700, temperature=0.0, seed=42)
                    hits = [e for e in expected if e in r["text"]]
                    false_pos = 1 if (mode == "distractor" and "42ZP" in r["text"]) else 0
                    case = {"ctx": ctx, "mode": mode, "depth": depth, "prompt_tokens": n,
                            "pass": 1 if len(hits) == len(expected) else 0,
                            "partial_hits": f"{len(hits)}/{len(expected)}", "false_pos_old_pw": false_pos,
                            "ttft_s": r["ttft_s"], "wall_s": r["wall_s"], "answer_head": r["text"][:100]}
                except Exception as e:
                    case = {"ctx": ctx, "mode": mode, "depth": depth, "pass": 0, "error": str(e)[:200]}
                rec["cases"].append(case)
                print(f"  ctx{ctx//1024}K {mode} d{depth}: pass={case.get('pass')} wall={case.get('wall_s')}", flush=True)
    rec["vram_peak"] = lab.vram_mib(gpu)
    rec["tps"] = lab.parse_tps(cname)
    rec["summary"] = {}
    for ctx in ctxs:
        cs = [c for c in rec["cases"] if c["ctx"] == ctx]
        rec["summary"][str(ctx)] = {"n": len(cs), "pass_rate": round(sum(c.get("pass", 0) for c in cs) / max(len(cs), 1), 3)}
    (lab.EVID / "runs" / "longctx").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "longctx" / f"{key}-needle.json", rec)
    lab.server_down(cname)
    rec.pop("cases", None)  # keep stdout print small
    return rec


if __name__ == "__main__":
    image, gpu, model_path, key, ctx_csv = sys.argv[1:6]
    extra_kv = sys.argv[6] if len(sys.argv) > 6 else ""
    port = int(sys.argv[7]) if len(sys.argv) > 7 else 18131
    out = run(image, gpu, model_path, key, [int(x) for x in ctx_csv.split(",")], extra_kv, port)
    print(json.dumps(out["summary"], ensure_ascii=False))
