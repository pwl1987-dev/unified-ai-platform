#!/usr/bin/env python3
"""SSE 流解析器 — 纯逻辑，可被单元/故障注入测试独立调用。

设计约束（METRICS-SCHEMA.md / v2.1 评审第 9 条）：
- 任意字节边界 feed 都不得崩溃或丢行（partial chunk 容忍）；
- malformed JSON 标记 malformed=true，不抛异常；
- [DONE] 事件独立 kind；重复事件照常产出（由计数层负责发现异常）；
- 解析器不负责计时。
"""
from __future__ import annotations

import json
from typing import Optional


class SSEParser:
    def __init__(self) -> None:
        self.buf = b""
        self.events: list[dict] = []

    def feed(self, chunk: bytes) -> list[dict]:
        """喂入任意切割的字节块，返回本次新完成的 SSE 事件。"""
        if not chunk:
            return []
        self.buf += chunk
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.rstrip(b"\r")
            ev = self._parse_line(line)
            if ev is not None:
                self.events.append(ev)
                out.append(ev)
        return out

    def flush(self) -> list[dict]:
        """流结束时处理残留缓冲（无换行结尾的最后一段）。"""
        out = []
        if self.buf:
            ev = self._parse_line(self.buf.rstrip(b"\r"))
            self.buf = b""
            if ev is not None:
                self.events.append(ev)
                out.append(ev)
        return out

    @staticmethod
    def _parse_line(line: bytes) -> Optional[dict]:
        if not line or line.startswith(b":"):
            return None  # 空行/SSE 注释
        if not line.startswith(b"data:"):
            return {"kind": "other", "raw": line.decode("utf-8", "replace")}
        payload = line[5:].strip()
        if payload == b"[DONE]":
            return {"kind": "done"}
        ev: dict = {"kind": "data", "payload": payload.decode("utf-8", "replace"),
                    "malformed": False}
        try:
            ev["json"] = json.loads(payload)
        except Exception:
            ev["malformed"] = True
        return ev


def extract_content(obj: dict) -> Optional[str]:
    """从 chat.completions chunk JSON 提取 delta 内容；无则 None。"""
    try:
        choices = obj.get("choices") or []
        if not choices:
            return None
        d = choices[0].get("delta") or {}
        c = d.get("content")
        return c if c else None
    except Exception:
        return None


def extract_finish_reason(obj: dict) -> Optional[str]:
    try:
        choices = obj.get("choices") or []
        return choices[0].get("finish_reason") if choices else None
    except Exception:
        return None
