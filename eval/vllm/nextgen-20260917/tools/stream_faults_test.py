#!/usr/bin/env python3
"""SSE 流协议故障注入测试（Harness Gate v2.1 第 9 条）。

七类故障：partial chunk / duplicated event / missing [DONE] / connection close
        / timeout / HTTP 500 / malformed JSON。
校验点：parser 不崩、不丢行、malformed 标记、事件计数正确。
全过输出 FAULTTEST_PASS。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sseparser import SSEParser, extract_content  # noqa: E402

FAILS = []


def ok(name, cond, detail=""):
    if not cond:
        FAILS.append(f"{name} {detail}")
    return cond


def chunk(content="A", extra=None):
    obj = {"id": "x", "choices": [{"index": 0, "delta": {"content": content},
                                   "finish_reason": None}]}
    if extra is not None:
        obj = extra
    return f"data: {json.dumps(obj)}\n\n".encode()


# 1. partial chunk：任意字节边界切割不丢行
p = SSEParser()
data = chunk("hello") + chunk("world") + b"data: [DONE]\n\n"
events = []
for i in range(len(data)):
    events += p.feed(data[i:i + 1])
events += p.flush()
data_events = [e for e in events if e["kind"] == "data"]
done_events = [e for e in events if e["kind"] == "done"]
ok("1 partial: no lost lines", len(data_events) == 2, f"got {len(data_events)}")
ok("1 partial: done seen", len(done_events) == 1)
ok("1 partial: contents", extract_content(data_events[0]["json"]) == "hello"
   and extract_content(data_events[1]["json"]) == "world")

# 2. duplicated event：照常产出两次（计数层负责发现）
p = SSEParser()
d = chunk("x")
ev2 = p.feed(d + d)
ok("2 duplicated", len([e for e in ev2 if e["kind"] == "data"]) == 2)

# 3. missing [DONE]：流结束 flush 仍能拿到全部 data 事件
p = SSEParser()
ev3 = p.feed(chunk("a") + chunk("b"))
ev3 += p.flush()
ok("3 no DONE", len([e for e in ev3 if e["kind"] == "data"]) == 2
   and not any(e["kind"] == "done" for e in ev3))

# 4. connection close mid-line：残行走 flush，不崩
p = SSEParser()
ev4 = p.feed(chunk("a") + b"data: {trunca")
ev4 += p.flush()
ok("4 close: survives", len(ev4) >= 1)
ok("4 close: truncated flagged malformed",
   ev4[-1].get("malformed") is True or ev4[-1]["kind"] == "other")

# 5. HTTP 500 / timeout：由 bench 层 HTTPError/timeout 异常路径处理；
#    此处验证 parser 对 500 页面 body（非 SSE）不崩
p = SSEParser()
ev5 = p.feed(b"<html>Internal Server Error</html>\n\n")
ok("5 http500 body: no crash", True)
ok("5 http500 body: other lines", all(e["kind"] in ("other",) for e in ev5))

# 6. malformed JSON：malformed 标记，不抛
p = SSEParser()
ev6 = p.feed(b"data: {not json at all\n\n")
ok("6 malformed flagged", ev6[0]["malformed"] is True)
ok("6 payload kept", "not json" in ev6[0]["payload"])

# 7. usage 事件（空 choices + usage）：extract_content 返回 None，不误计 token
usage_obj = {"id": "x", "choices": [],
             "usage": {"prompt_tokens": 565, "completion_tokens": 512}}
p = SSEParser()
ev7 = p.feed(f"data: {json.dumps(usage_obj)}\n\n".encode())
ok("7 usage: not a token", extract_content(ev7[0]["json"]) is None)
ok("7 usage: parsed", ev7[0]["json"]["usage"]["completion_tokens"] == 512)

# 8. CRLF 兼容
p = SSEParser()
ev8 = p.feed(chunk("c").replace(b"\n\n", b"\r\n\r\n"))
ok("8 crlf", len([e for e in ev8 if e["kind"] == "data"]) == 1)

print("\n".join(FAILS) if FAILS else "all fault-injection cases passed")
print("FAULTTEST_" + ("FAIL" if FAILS else "PASS"))
sys.exit(1 if FAILS else 0)
