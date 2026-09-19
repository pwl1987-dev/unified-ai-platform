#!/usr/bin/env python3
"""P1-SCR-BATCH2 单元工具 A：尾部改写 / 多轮 / churn 存活（match-unit + retention 两向共用）。

fixture 纪律（token 级构造 + 双重校验）：
  1) 尾段精确 n token：逐字贪心拼到 enc(tail) == n 个 id；
  2) 变体级校验：enc(prefix_text+tail_text) 必须以 base 前 b 个 id 开头且总长 b+n
     （seam 合并则 b 回退，实际 shared/rewrite 如实记录）。
  fixture 全部冻结进 sandbox 缓存（version 3），各臂共用 —— 跨臂可比性由同一 fixture 集保证。
cache_salt 语义（0.29 源码 kv_cache_utils.py:604-612）：salt 只进首块哈希 ——
  同 salt+同前缀=共享；异 salt=全断（冷形态）。

单元（每 boot 内自控）：
  cold_ref   冷参照 ×reps（逐 rep 唯一 salt，内容=base）
  warm_full  暖全命中 ×reps（salt S0；rep1 兼作预热）
  rw_N       尾部改写 N∈{1,8,32,128} ×reps（salt S0，尾部逐 rep 不同 → 每次 true partial）
  multiturn  K=5 轮增长式对话（p4k 基，逐轮 TTFT；单 user 消息增长=多轮共享代理）
  churn      J 个唯一 salt p4k 灌满后暖复访 → warm_after_churn TTFT

用法: p1_batch2_tailrw.py --port 19702 --arm-key MU32 --reps 3 --churn 40 \
        [--skip-multiturn] [--skip-churn] --server-pid P --tag t
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gen_fixtures import make_prompt  # noqa: E402

SBX = "/data/sandbox/nextgen-20260917"
STAGING = os.path.join(NEXTGEN, "raw", "staging")
FIX_CACHE = os.path.join(SBX, "p1-batch2-fixtures.json")
VENV_PY = "/data/tools/vllm29-env/bin/python"
MODEL_DIR = "/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128"
REWRITES = (1, 8, 32, 128)
N_REP_VARIANTS = 4          # 每 n 冻结 4 个变体（3 正式 + 1 备用）
CHAR_POOL = ("改写段编号补充纪要尾部测量内容随变化避免缓存复用本轮继续登记备案要点"
             "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地玄黄宇宙洪荒日月盈昃")


# ---------------------------------------------------------------- tokenizer 工作进程

TOK_CODE = """
import json, sys
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(r'@@MODEL@@', trust_remote_code=True)
def enc(t): return tok.encode(t, add_special_tokens=False)
def dec(ids): return tok.decode(ids)
print(json.dumps({'probe': enc('登记码941235已备案。')[:3]})); sys.stdout.flush()
while True:
    line = sys.stdin.readline()
    if not line: break
    q = json.loads(line)
    if q['op'] == 'enc':
        r = {'ids': enc(q['text'])}
    elif q['op'] == 'dec':
        r = {'text': dec(q['ids']), 'rt': enc(dec(q['ids'])) == q['ids']}
    sys.stdout.write(json.dumps(r) + '\\n'); sys.stdout.flush()
""".replace("@@MODEL@@", MODEL_DIR)


class TokWorker:
    def __init__(self) -> None:
        self.proc = subprocess.Popen([VENV_PY, "-c", TOK_CODE], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
        hello = json.loads(self.proc.stdout.readline())
        if "probe" not in hello:
            raise SystemExit("tokenizer worker boot failed")

    def enc(self, text: str) -> list[int]:
        self.proc.stdin.write(json.dumps({"op": "enc", "text": text}) + "\n")
        return json.loads(self.proc.stdout.readline())["ids"]

    def dec_rt(self, ids: list[int]) -> tuple[str, bool]:
        self.proc.stdin.write(json.dumps({"op": "dec", "ids": ids}) + "\n")
        r = json.loads(self.proc.stdout.readline())
        return r["text"], r["rt"]

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass


def exact_token_tail(w: TokWorker, n: int, seed_offset: int) -> str:
    """贪心拼字直到 enc(tail) 恰好 n 个 id；起始偏移保证逐变体不同。"""
    acc = ""
    i = seed_offset
    while True:
        need = n - len(w.enc(acc))
        if need == 0:
            return acc
        c = CHAR_POOL[i % len(CHAR_POOL)]
        i += 7
        acc += c
        if len(w.enc(acc)) > n:      # 某字占 2 id 超额 → 回退换下一个字
            acc = acc[:-1]
            i += 13


def build_fixtures() -> dict:
    if os.path.exists(FIX_CACHE):
        cached = json.load(open(FIX_CACHE))
        if cached.get("version") == 3:
            return cached
    w = TokWorker()
    out: dict = {"version": 3, "model_dir": MODEL_DIR, "fixtures": {}}
    for name, target in (("d565rw", 565), ("p4krw", 4096)):
        base_text = make_prompt(target)
        ids = w.enc(base_text)
        variants: dict = {}
        for n in REWRITES:
            vs = []
            for vi in range(N_REP_VARIANTS):
                tail = exact_token_tail(w, n, seed_offset=vi * 31 + n)
                b = len(ids) - n
                for _ in range(10):          # 变体级校验 + seam 回退
                    prefix_text, _rt = w.dec_rt(ids[:b])
                    vtext = prefix_text + tail
                    vids = w.enc(vtext)
                    if vids[:b] == ids[:b] and len(vids) == b + len(w.enc(tail)):
                        break
                    b -= 1
                vs.append({"text": vtext, "shared_tokens": b,
                           "rewrite_tokens": len(vids) - b})
            variants[str(n)] = vs
        out["fixtures"][name] = {"target": target, "base_text": base_text,
                                 "base_tokens": len(ids), "variants": variants}
        print(f"[fixture] {name}: base {len(ids)} tok, rewrites frozen", flush=True)
    w.close()
    json.dump(out, open(FIX_CACHE, "w"), ensure_ascii=False)
    return out


# ---------------------------------------------------------------- 请求执行

def stream_once(api: str, pload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(api + "/chat/completions",
                                 data=json.dumps(pload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first = None
    n_tok = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                if line[6:] == "[DONE]":
                    break
                obj = json.loads(line[6:])
                d = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                if d:
                    n_tok += 1
                    if first is None:
                        first = time.monotonic()
        return {"ok": True, "http": 200,
                "ttft": round(first - t0, 4) if first else None,
                "tokens": n_tok, "wall": round(time.monotonic() - t0, 3)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "err": f"HTTP{e.code}",
                "ttft": None, "tokens": 0, "wall": round(time.monotonic() - t0, 3)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "http": None, "err": str(e)[:120],
                "ttft": None, "tokens": 0, "wall": round(time.monotonic() - t0, 3)}


def payload(text: str, salt: str, mt: int = 8) -> dict:
    return {"model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": text}],
            "max_tokens": mt, "stream": True, "cache_salt": salt}


# ---------------------------------------------------------------- 单元执行

def med(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 4) if vals else None


def run_cells(api: str, arm_key: str, fx_all: dict, reps: int, churn_n: int,
              multiturn: bool, tag: str) -> dict:
    out: dict = {"arm": arm_key, "tag": tag, "ts": time.strftime("%F %T")}
    S0 = f"b2-{arm_key.lower()}-s0"
    for name in ("d565rw", "p4krw"):
        fx = fx_all["fixtures"][name]
        base = fx["base_text"]
        cells: dict = {}
        tt = []
        for r in range(1, reps + 1):
            res = stream_once(api, payload(base, f"{S0}-cold-{r}-{time.time_ns() % 10**6}"))
            tt.append(res["ttft"] if res["ok"] else None)
            time.sleep(1)
        cells["cold_ref"] = {"ttfts": tt, "med": med(tt)}
        tt = []
        for r in range(1, reps + 1):
            res = stream_once(api, payload(base, S0))
            tt.append(res["ttft"] if res["ok"] else None)
            time.sleep(1)
        cells["warm_full"] = {"ttfts": tt, "med": med(tt)}
        for n_str, vs in fx["variants"].items():
            tt, oks = [], []
            for r in range(reps):
                v = vs[r]
                res = stream_once(api, payload(v["text"], S0))
                tt.append(res["ttft"] if res["ok"] else None)
                oks.append(res["ok"])
                time.sleep(1)
            cells[f"rw_{n_str}"] = {
                "ttfts": tt, "med": med(tt), "all_ok": all(oks),
                "shared": [v["shared_tokens"] for v in vs[:reps]],
                "rewrite": [v["rewrite_tokens"] for v in vs[:reps]]}
        out[name] = cells
    if multiturn:
        turns = []
        conv = fx_all["fixtures"]["p4krw"]["base_text"]
        for k in range(1, 6):
            if k > 1:
                conv += (f"\n\n[纪要{ k - 1}] 已记录上述要点，登记码 {900000 + k}。"
                         f"\n\n[问{k}] 请基于此前全部内容给出第 {k} 轮摘要。")
            res = stream_once(api, payload(conv, f"{S0}-mt"))
            turns.append({"turn": k, "ttft": res["ttft"] if res["ok"] else None,
                          "ok": res["ok"]})
            time.sleep(1)
        out["multiturn"] = turns
    if churn_n > 0:
        base4k = fx_all["fixtures"]["p4krw"]["base_text"]
        for j in range(churn_n):
            stream_once(api, payload(base4k, f"{S0}-churn-{j}-{time.time_ns() % 10**6}"))
        res = stream_once(api, payload(base4k, S0))
        out["churn"] = {"churn_reqs": churn_n,
                        "warm_after_churn_ttft": res["ttft"] if res["ok"] else None}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=19702)
    ap.add_argument("--arm-key", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--churn", type=int, default=40)
    ap.add_argument("--skip-multiturn", action="store_true")
    ap.add_argument("--skip-churn", action="store_true")
    ap.add_argument("--server-pid", type=int)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    api = f"http://127.0.0.1:{args.port}/v1"
    fx = build_fixtures()
    doc = run_cells(api, args.arm_key, fx, args.reps,
                    0 if args.skip_churn else args.churn,
                    not args.skip_multiturn, args.tag or args.arm_key)
    if args.server_pid:
        doc["server_pid"] = args.server_pid
    dest = os.path.join(STAGING, "P02-SCREEN", f"p1-batch2-{args.arm_key.lower()}-cells.json")
    json.dump(doc, open(dest, "w"), indent=1, ensure_ascii=False)
    brief = {}
    for fx_name in ("d565rw", "p4krw"):
        c = doc.get(fx_name, {})
        brief[fx_name] = {k: v.get("med") for k, v in c.items() if isinstance(v, dict)}
    print(json.dumps(brief, ensure_ascii=False))
    print(f"written {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
