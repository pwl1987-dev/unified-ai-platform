#!/usr/bin/env python3
"""Phase 04 — 确定性 tool/JSON schema micro-suite（safety gate，不冒充 BFCL）。

20 条固定任务：每条 = 提示 + 机器可验判据（json_schema / exact_keys / regex 三型）。
判据确定性（无 LLM 评分、无 RNG）；失败=结构性破坏（否决级），通过=仅结构安全。
数据角色：screen 与 holdout 阶段共用（回归门属性，非判别集）。
用法：ph4_tooljson_micro.py --api http://127.0.0.1:PORT/v1 --out <json> [--model NAME]
自测（--selftest）：判据器对构造响应的判定正确性。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

SUITE = [
    {"id": "tj01", "kind": "json_schema", "prompt": "输出一个 JSON 对象，恰好两个键 name(string) 与 age(int)。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["name", "age"], "types": {"name": "str", "age": "int"}, "exact_keys": True}},
    {"id": "tj02", "kind": "json_schema", "prompt": "输出 JSON 数组，含恰好 3 个整数。只输出 JSON。",
     "check": {"type": "array", "length": 3, "elem_type": "int"}},
    {"id": "tj03", "kind": "exact_keys", "prompt": '输出 JSON：{"status":"ok","items":[1,2]}。只输出该 JSON。',
     "check": {"keys": {"status": "ok", "items_len": 2}}},
    {"id": "tj04", "kind": "json_schema", "prompt": "输出一个 JSON 对象：键 tool(string)、args(object)。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["tool", "args"], "types": {"tool": "str", "args": "dict"}}},
    {"id": "tj05", "kind": "json_schema", "prompt": "输出 JSON 对象：key=str(仅小写字母)，value=list[str](恰好2个)。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["key", "value"], "types": {"key": "str", "value": "list"}, "list_len": {"value": 2}}},
    {"id": "tj06", "kind": "regex", "prompt": "只输出一个形如 ABC-1234 的登记码（大写字母三连-数字四连），不要其他内容。",
     "check": {"pattern": r"^[A-Z]{3}-\d{4}$"}},
    {"id": "tj07", "kind": "json_schema", "prompt": "输出 JSON：{ \"result\": \"PASS\", \"detail\": {\"n\": 5} }。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["result", "detail"], "consts": {"result": "PASS"}}},
    {"id": "tj08", "kind": "array_of_objects", "prompt": "输出 JSON 数组，含 2 个对象，各含 id(int) 与 done(bool)。只输出 JSON。",
     "check": {"type": "array", "length": 2, "elem_required": ["id", "done"], "elem_types": {"id": "int", "done": "bool"}}},
    {"id": "tj09", "kind": "exact_keys", "prompt": '输出 JSON：{"mode":"tool","count":0}。只输出该 JSON。',
     "check": {"keys": {"mode": "tool", "count": 0}}},
    {"id": "tj10", "kind": "json_schema", "prompt": "输出 JSON 对象：payload 为嵌套对象含 inner(string)。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["payload"], "nested": {"payload": {"required_keys": ["inner"], "types": {"inner": "str"}}}}},
    {"id": "tj11", "kind": "json_schema", "prompt": "输出 JSON：{ \"nums\": [1,2,3,4,5] }。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["nums"], "types": {"nums": "list"}, "list_len": {"nums": 5}, "elem_type_at": {"nums": "int"}}},
    {"id": "tj12", "kind": "regex", "prompt": "只输出 32 位小写十六进制串（无空格无换行）。",
     "check": {"pattern": r"^[0-9a-f]{32}$"}},
    {"id": "tj13", "kind": "json_schema", "prompt": "输出 JSON 对象：op∈{add,mul}，a(int)，b(int)。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["op", "a", "b"], "types": {"op": "str", "a": "int", "b": "int"}, "enum": {"op": ["add", "mul"]}}},
    {"id": "tj14", "kind": "exact_keys", "prompt": '输出 JSON：{"ok":true,"n_errors":0}。只输出该 JSON。',
     "check": {"keys": {"ok": True, "n_errors": 0}}},
    {"id": "tj15", "kind": "array_of_objects", "prompt": "输出 3 个对象的 JSON 数组，各含 tag(string)。只输出 JSON。",
     "check": {"type": "array", "length": 3, "elem_required": ["tag"], "elem_types": {"tag": "str"}}},
    {"id": "tj16", "kind": "json_schema", "prompt": "输出 JSON：{ \"config\": {\"seed\": 42, \"strict\": true} }。只输出 JSON。",
     "check": {"type": "object", "nested": {"config": {"required_keys": ["seed", "strict"], "consts": {"seed": 42, "strict": True}}}}},
    {"id": "tj17", "kind": "json_schema", "prompt": "输出 JSON 对象：words=list[str] 恰好 4 个非空串。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["words"], "list_len": {"words": 4}, "elem_nonempty": "words"}},
    {"id": "tj18", "kind": "regex", "prompt": "只输出 IPv4 地址（形如 192.168.1.1），无其他内容。",
     "check": {"pattern": r"^(\d{1,3}\.){3}\d{1,3}$"}},
    {"id": "tj19", "kind": "exact_keys", "prompt": '输出 JSON：{"level":"warn","code":2001}。只输出该 JSON。',
     "check": {"keys": {"level": "warn", "code": 2001}}},
    {"id": "tj20", "kind": "json_schema", "prompt": "输出 JSON 对象：含 data(list) 与 meta(object)。只输出 JSON。",
     "check": {"type": "object", "required_keys": ["data", "meta"], "types": {"data": "list", "meta": "dict"}}},
]


def _t(v):
    return {int: "int", bool: "bool", str: "str", dict: "dict", list: "list"}.get(type(v))


def extract_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t), None
    except json.JSONDecodeError as e:
        return None, f"JSON decode: {e}"


def validate(item: dict, text: str) -> tuple[bool, str]:
    chk = item["check"]
    if item["kind"] == "regex":
        return (bool(re.match(chk["pattern"], text.strip())), "pattern mismatch" )
    obj, err = extract_json(text)
    if obj is None:
        return False, err
    if chk.get("type") == "object":
        if not isinstance(obj, dict):
            return False, "not object"
        for k in chk.get("required_keys", []):
            if k not in obj:
                return False, f"missing key {k}"
        if chk.get("exact_keys") and set(obj) != set(chk["required_keys"]):
            return False, "extra keys"
        for k, t in (chk.get("types") or {}).items():
            if k in obj and _t(obj[k]) != t:
                return False, f"{k} type {_t(obj[k])}!={t}"
        for k, v in (chk.get("consts") or {}).items():
            if obj.get(k) != v:
                return False, f"{k} const mismatch"
        for k, v in (chk.get("enum") or {}).items():
            if obj.get(k) not in v:
                return False, f"{k} not in enum"
        for k, n in (chk.get("list_len") or {}).items():
            if not isinstance(obj.get(k), list) or len(obj[k]) != n:
                return False, f"{k} len mismatch"
        for k, t in (chk.get("elem_type_at") or {}).items():
            if not all(_t(x) == t for x in obj.get(k, [])):
                return False, f"{k} elem type"
        for k in (chk.get("elem_nonempty") or []):
            if not all(isinstance(x, str) and x for x in obj.get(k, [])):
                return False, f"{k} empty elem"
        for parent, sub in (chk.get("nested") or {}).items():
            node = obj.get(parent)
            if not isinstance(node, dict):
                return False, f"{parent} not object"
            for k in sub.get("required_keys", []):
                if k not in node:
                    return False, f"{parent}.{k} missing"
            for k, v in (sub.get("consts") or {}).items():
                if node.get(k) != v:
                    return False, f"{parent}.{k} const"
        return True, ""
    if chk.get("type") == "array":
        if not isinstance(obj, list) or len(obj) != chk.get("length", -1):
            return False, "array shape"
        et = chk.get("elem_type")
        if et and not all(_t(x) == et for x in obj):
            return False, "elem type"
        for k in chk.get("elem_required", []):
            if not all(isinstance(x, dict) and k in x for x in obj):
                return False, f"elem missing {k}"
        for k, t in (chk.get("elem_types") or {}).items():
            if not all(isinstance(x, dict) and _t(x.get(k)) == t for x in obj):
                return False, f"elem {k} type"
        return True, ""
    if item["kind"] == "exact_keys":
        want = chk["keys"]
        if not isinstance(obj, dict):
            return False, "not object"
        for k, v in want.items():
            got = obj.get(k)
            if k.endswith("_len"):
                continue
            if isinstance(v, int) and _t(got) == "int":
                if got != v:
                    return False, f"{k} mismatch"
            elif got != v:
                return False, f"{k} mismatch"
        for k, n in want.items():
            if k.endswith("_len") and len(obj.get(k[:-4], [])) != n:
                return False, f"{k} len"
        return True, ""
    return False, "unknown kind"


def selftest() -> int:
    ok = True
    for it, good in ((SUITE[0], '{"name":"x","age":1}'),
                     (SUITE[0], '{"name":"x","age":1,"extra":2}'),
                     (SUITE[1], "[1,2,3]"), (SUITE[5], "ABC-1234"), (SUITE[5], "abc-123")):
        passed, _ = validate(it, good)
        print(it["id"], repr(good)[:30], "->", passed)
    r1 = validate(SUITE[0], '{"name":"x","age":1}')[0]
    r2 = validate(SUITE[0], '{"name":"x","age":1,"extra":2}')[0] if SUITE[0]["check"].get("exact_keys") else True
    r3 = validate(SUITE[5], "ABC-1234")[0]
    r4 = validate(SUITE[5], "abc-123")[0]
    ok = r1 and r2 is False and r3 and r4 is False
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def run(api: str, out: str, model: str) -> int:
    results = []
    for it in SUITE:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": it["prompt"]}],
                           "max_tokens": 200, "temperature": 0, "stream": False}).encode()
        req = urllib.request.Request(api + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                obj = json.loads(r.read())
            text = (obj.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
            passed, why = validate(it, text)
        except Exception as e:  # noqa: BLE001
            text, passed, why = "", False, repr(e)[:120]
        results.append({"id": it["id"], "passed": passed, "why": why,
                        "text_head": text[:80], "latency_s": round(time.monotonic() - t0, 2)})
        print(f"[{it['id']}] {'PASS' if passed else 'FAIL ' + why}")
    n_pass = sum(r["passed"] for r in results)
    verdict = {"STRUCTURAL_SAFE" if n_pass == len(SUITE)
               else "STRUCTURAL_FAIL" if n_pass < len(SUITE) - 2 else "PARTIAL_REVIEW"}
    rep = {"suite": "tool-json-micro-v1", "n_pass": n_pass, "n_total": len(SUITE),
           "verdict": verdict[0], "role": "safety gate（不冒充 BFCL）",
           "results": results}
    json.dump(rep, open(out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"verdict": verdict[0], "n_pass": n_pass}))
    return 0 if verdict[0] == "STRUCTURAL_SAFE" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--api")
    ap.add_argument("--out", default="tooljson-micro-result.json")
    ap.add_argument("--model", default="qwen3.8-27b")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.api:
        return run(a.api, a.out, a.model)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
