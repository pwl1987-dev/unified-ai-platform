"""agent.py — AGENT-SUITE: simulated tool env, multi-turn, machine-scored.
Scenarios: single/multi/dependent tools, wrong-tool trap, missing-info, failure recovery,
malformed result, 8/16/32-turn persistence.
Usage: uv run python agent.py <image> <gpu> <model_path> <model_key> [port]
"""
from __future__ import annotations
import json, re, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab
import httpx

TOOLS = [
    {"type": "function", "function": {"name": "get_weather", "description": "查询城市当前天气",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {"name": "query_db", "description": "在订单库执行只读 SQL 查询",
     "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}},
    {"type": "function", "function": {"name": "send_email", "description": "发送邮件",
     "parameters": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"},
                                                    "body": {"type": "string"}}, "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {"name": "file_read", "description": "读取实验服务器上的文本文件",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
]


def fake_tool(name: str, args: dict, state: dict):
    """Deterministic simulated tool world."""
    if name == "get_weather":
        table = {"北京": "晴 12C", "上海": "小雨 18C", "广州": "多云 26C", "深圳": "多云 27C"}
        c = args.get("city", "")
        for k, v in table.items():
            if k in c:
                return {"city": k, "weather": v}
        return {"error": f"unknown city {c}"}
    if name == "query_db":
        sql = args.get("sql", "")
        if "order_88231" in sql:
            return {"rows": [{"order_id": 88231, "status": "PAID", "amount": 1299.0, "user": "u_772"}]}
        if "u_772" in sql.lower() or "user" in sql.lower():
            return {"rows": [{"order_id": 88231, "status": "PAID", "amount": 1299.0, "user": "u_772"},
                             {"order_id": 88232, "status": "REFUNDED", "amount": 89.0, "user": "u_772"}]}
        if "count" in sql.lower() or "*" in sql:
            return {"rows": [{"cnt": 2}]}
        return {"rows": []}
    if name == "send_email":
        state["emails"] = state.get("emails", []) + [args]
        return {"queued": True, "id": f"mail-{len(state['emails'])}"}
    if name == "file_read":
        table = {"/etc/motd": "Welcome to bench-node-07\n",
                 "/var/log/app.txt": "2026-09-26 08:00:01 INFO boot ok\n2026-09-26 08:05:44 WARN disk /data at 91%\n",
                 "/data/notes.txt": "会议纪要：周四发布 v2；负责人老王。\n"}
        p = args.get("path", "")
        if p in table:
            return {"content": table[p]}
        return {"error": "ENOENT"}
    return {"error": "unknown tool"}


def run_episode(port: int, msgs: list, state: dict, max_rounds: int = 8, extra_first: dict | None = None):
    """Drive a tool-use episode; returns (final_text, rounds, tool_calls_made)."""
    calls_made = []
    for rnd in range(max_rounds):
        r = httpx.post(f"http://127.0.0.1:{port}/v1/chat/completions", timeout=600, json={
            "messages": msgs, "max_tokens": 800, "temperature": 0.0, "seed": 42,
            "tools": TOOLS, "tool_choice": "auto"})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        tcs = msg.get("tool_calls") or []
        if not tcs:
            return msg.get("content") or "", rnd + 1, calls_made
        msgs = msgs + [{"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs}]
        for tc in tcs:
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            calls_made.append((fn.get("name"), args))
            res = fake_tool(fn.get("name", ""), args, state)
            msgs = msgs + [{"role": "tool", "tool_call_id": tc.get("id", ""), "content": json.dumps(res, ensure_ascii=False)}]
    return "", max_rounds, calls_made


def sc_single(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content": "北京现在天气怎么样？"}], {})
    ok = any(n == "get_weather" and "北京" in str(a) for n, a in calls) and "晴" in txt
    return {"pass": ok, "calls": calls[:2], "rounds": rnds, "final_head": txt[:80]}


def sc_multi(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content": "对比北京和上海现在的天气，一句话结论。"}], {})
    cities = {str(a.get("city", "")) for n, a in calls if n == "get_weather"}
    ok = any("北京" in c for c in cities) and any("上海" in c for c in cities) and ("晴" in txt or "雨" in txt)
    return {"pass": ok, "cities": sorted(cities), "rounds": rnds}


def sc_dependent(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content":
        "查订单 88231 的状态和金额；然后把结果发邮件给 ops@x.com，主题'订单88231状态'。"}], {})
    names = [n for n, _ in calls]
    st = {}
    ok = ("query_db" in names and "send_email" in names
          and any("88231" in str(a.get("subject", "")) + str(a.get("body", "")) or "PAID" in str(a.get("body", "")) for n, a in calls if n == "send_email")
          and ("1299" in txt or "PAID" in txt or st.get("emails")))
    return {"pass": 1 if ok else 0, "chain": names, "rounds": rnds, "final_head": txt[:100]}


def sc_trap(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content": "法国的首都是哪里？"}], {})
    ok = len(calls) == 0 and "巴黎" in txt
    return {"pass": ok, "calls": calls[:2], "note": "no tool should fire", "final_head": txt[:60]}


def sc_missing(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content": "帮我查一下天气。"}], {})
    asked = "?" in txt or "？" in txt or "哪个城市" in txt
    ok = asked or (calls and calls[0][0] == "get_weather" and calls[0][1].get("city") not in (None, ""))
    return {"pass": 1 if ok else 0, "asked": 1 if asked else 0, "final_head": txt[:80]}


def sc_failure_recovery(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content": "查一下东京的天气，如果没有就直接告诉我查不到。"}], {})
    ok = ("查不到" in txt or "无法" in txt or "没有" in txt) and not any("晴" in txt or "雨" in txt for _ in [0])
    return {"pass": 1 if ok else 0, "final_head": txt[:80], "rounds": rnds}


def sc_malformed(port):
    txt, rnds, calls = run_episode(port, [{"role": "user", "content": "读取 /var/log/app.txt 并告诉我有没有 WARN。"}], {})
    ok = "WARN" in txt and ("91%" in txt or "disk" in txt)
    return {"pass": 1 if ok else 0, "final_head": txt[:80]}


def sc_long_turns(port, turns):
    facts = {}
    msgs = [{"role": "system", "content": "你是运维助手。全程只用中文回答。"}]
    score_events = []
    for t in range(turns):
        if t == 1:
            q = "记住：我们的发布窗口是每周四 03:15。"
            facts["window"] = "03:15"
        elif t == turns - 1:
            q = "我们的发布窗口是几点？（不要调用工具，直接回答，只输出时间）"
        elif t == 2:
            q = "北京天气如何？"
        elif t == turns - 5:
            q = "/etc/motd 里写的节点名是什么？"
        elif t % 3 == 0:
            q = f"第{t}轮：用一句话说明你都配置了哪些工具。"
        else:
            q = f"第{t}轮：简短确认。"
        msgs.append({"role": "user", "content": q})
        txt, rnds, calls = run_episode(port, msgs, {}, max_rounds=4)
        msgs.append({"role": "assistant", "content": txt or "(tool)"})
        if t == turns - 1:
            score_events.append(("memory", 1 if facts.get("window", "") in txt else 0, txt[:60]))
        if t == 2:
            score_events.append(("tool_mid", 1 if any(n == "get_weather" for n, _ in calls) else 0, ""))
        if t == turns - 5:
            score_events.append(("file_late", 1 if "bench-node-07" in txt or "motd" in txt.lower() else 0, txt[:60]))
        if t == turns - 2:
            zh = len(re.findall(r"[\u4e00-\u9fff]", txt)) > max(2, len(txt) * 0.3)
            score_events.append(("zh_persist", 1 if zh else 0, ""))
    ok = all(s for _, s, _ in score_events) if score_events else 0
    return {"pass": ok, "events": score_events, "turns": turns}


SCENARIOS = [("single", sc_single), ("multi", sc_multi), ("dependent", sc_dependent), ("trap", sc_trap),
             ("missing_info", sc_missing), ("failure_recovery", sc_failure_recovery), ("malformed", sc_malformed),
             ("turns_8", lambda p: sc_long_turns(p, 8)), ("turns_16", lambda p: sc_long_turns(p, 16)),
             ("turns_32", lambda p: sc_long_turns(p, 32))]


def main():
    image, gpu, model_path, key = sys.argv[1:5]
    port = int(sys.argv[5]) if len(sys.argv) > 5 else 18171
    cname = f"agent-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c 65536 -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a agent -b 512 -ub 512 --metrics")
    rec = {"model": key, "scenarios": []}
    lab.server_up(cname, image, port, gpu, cmd)
    time.sleep(2)
    for attempt in range(3):
        try:
            lab.chat_nonstream(port, [{"role": "user", "content": "ping"}], max_tokens=16)
            break
        except Exception:
            time.sleep(3)
    for name, fn in SCENARIOS:
        try:
            r = fn(port)
        except Exception as e:
            r = {"pass": 0, "error": str(e)[:200]}
        r["id"] = name
        rec["scenarios"].append(r)
        print(f"  {name}: pass={r.get('pass')}", flush=True)
    rec["score"] = sum(s["pass"] for s in rec["scenarios"])
    rec["tps"] = lab.parse_tps(cname)
    (lab.EVID / "runs" / "agent").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "agent" / f"{key}.json", rec)
    lab.server_down(cname)
    print(f"AGENT SCORE {rec['score']}/{len(rec['scenarios'])}")


if __name__ == "__main__":
    main()
