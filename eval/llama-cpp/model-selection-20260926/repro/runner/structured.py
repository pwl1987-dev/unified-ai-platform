"""structured.py — STRUCTURED-OUTPUT-SUITE: strict/nested JSON, schema, enums, arrays,
nullable/optional, nested tool args, fenced markdown, no-prose contract.
Usage: uv run python structured.py <image> <gpu> <model_path> <model_key> [port]
"""
from __future__ import annotations
import json, re, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab
import jsonschema

CASES = [
    {"id": "strict_flat", "prompt": '只输出 JSON 对象，不要任何其他文字：{"ok":true,"n":42,"tags":["a","b"]}',
     "schema": {"type": "object", "properties": {"ok": {"const": True}, "n": {"const": 42},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 2}},
                "required": ["ok", "n", "tags"], "additionalProperties": False},
     "json_mode": True, "no_prose": True},
    {"id": "nested_deep", "prompt": '输出 JSON：用户档案含姓名、年龄、地址(省/市/街道)、两个联系人(姓名+电话)。姓名=张伟,年龄=34,省=山东,市=临沂,街道=兰山路人行,联系人=李雷13800000001/韩梅梅13900000002。只输出 JSON。',
     "schema": {"type": "object", "properties": {"name": {"const": "张伟"}, "age": {"const": 34},
                "address": {"type": "object", "properties": {"province": {"const": "山东"}, "city": {"const": "临沂"}},
                            "required": ["province", "city"]},
                "contacts": {"type": "array", "minItems": 2, "items": {"type": "object",
                             "properties": {"phone": {"type": "string"}}, "required": ["phone"]}}},
                "required": ["name", "age", "address", "contacts"]}},
    {"id": "enum_array_nullable", "prompt": '输出 JSON：{"level": 枚举 debug|info|warn|error 选 "warn", "items": [1,2,3], "note": null, "ratio": 0.5}。只输出 JSON。',
     "schema": {"type": "object", "properties": {"level": {"enum": ["debug", "info", "warn", "error"]},
                "items": {"const": [1, 2, 3]}, "note": {"type": "null"}, "ratio": {"const": 0.5}},
                "required": ["level", "items", "note", "ratio"]}, "json_mode": True},
    {"id": "optional_field", "prompt": '输出 JSON：{"id":"x1","status":"done"}；只有当有错误时才加 "error" 字段（现在没有错误）。只输出 JSON。',
     "schema": {"type": "object", "properties": {"id": {"const": "x1"}, "status": {"const": "done"}},
                "required": ["id", "status"], "not": {"required": ["error"]}}, "json_mode": True},
    {"id": "markdown_fenced", "prompt": "输出一个 markdown 代码块（```json 开头），内容为 {\"a\":1}。代码块外不要有任何文字。",
     "extract": r"```json\s*(.*?)\s*```", "schema": {"type": "object", "properties": {"a": {"const": 1}}, "required": ["a"]},
     "no_prose": True},
    {"id": "xml_like", "prompt": "输出 XML 风格契约（不是 JSON）：<result><code>200</code><items>3</items></result>。只输出该行。",
     "extract": r"<result>(.*?)</result>", "need": ["<code>200</code>", "<items>3</items>"], "no_prose": True},
    {"id": "big_array_50", "prompt": "输出 JSON：数组含 50 个对象，每个 {\"id\": 序号, \"flag\": true}。只输出 JSON。",
     "schema": {"type": "array", "minItems": 50, "maxItems": 50, "items": {"type": "object",
                "properties": {"id": {"type": "integer"}, "flag": {"const": True}}, "required": ["id", "flag"]}},
     "json_mode": True},
]

TOOL_NESTED = [{"type": "function", "function": {"name": "deploy_stack",
    "parameters": {"type": "object", "properties": {
        "name": {"type": "string"},
        "replicas": {"type": "integer"},
        "resources": {"type": "object", "properties": {"cpu": {"type": "number"}, "mem_gb": {"type": "integer"}},
                       "required": ["cpu", "mem_gb"]},
        "env": {"type": "object", "additionalProperties": {"type": "string"}}},
        "required": ["name", "replicas", "resources"]}}}]


def try_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
        if m:
            t = m.group(1).strip()
    return json.loads(t)


def main():
    image, gpu, model_path, key = sys.argv[1:5]
    port = int(sys.argv[5]) if len(sys.argv) > 5 else 18161
    cname = f"struct-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c 32768 -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a struct -b 512 -ub 512 --metrics")
    rec = {"model": key, "cases": []}
    lab.server_up(cname, image, port, gpu, cmd)
    time.sleep(2)
    for attempt in range(3):
        try:
            lab.chat_nonstream(port, [{"role": "user", "content": "ping"}], max_tokens=16)
            break
        except Exception:
            time.sleep(3)
    valid_json = schema_valid = contract = 0
    for c in CASES:
        extra = {"response_format": {"type": "json_object"}} if c.get("json_mode") else None
        try:
            r = lab.chat(port, [{"role": "user", "content": c["prompt"]}], max_tokens=1500, temperature=0.0, seed=42, extra=extra)
            text = r["text"]
            case = {"id": c["id"], "wall_s": r["wall_s"], "reasoning_chars": r["reasoning_chars"]}
            payload = None
            if "extract" in c:
                m = re.search(c["extract"], text, re.S)
                inner = m.group(1) if m else text
                if "need" in c:
                    case["pass"] = 1 if all(n in inner for n in c["need"]) else 0
                elif inner.strip().startswith("{"):
                    payload = try_json(inner)
                    case["pass"] = 1
                else:
                    case["pass"] = 0
            else:
                try:
                    payload = try_json(text)
                    valid_json += 1
                    case["pass"] = 1
                except Exception as e:
                    case["pass"] = 0
                    case["err"] = f"json: {str(e)[:100]}"
            if payload is not None and "schema" in c:
                try:
                    jsonschema.validate(payload, c["schema"])
                    schema_valid += 1
                    case["schema_ok"] = 1
                    case["pass"] = 1
                except Exception as e:
                    case["schema_ok"] = 0
                    case["pass"] = 0
                    case["err"] = f"schema: {str(e)[:120]}"
            if c.get("no_prose"):
                stripped = text.strip()
                ok_prose = stripped.startswith("{") or stripped.startswith("<result>") or stripped.startswith("```")
                case["no_prose_ok"] = 1 if ok_prose else 0
                if not ok_prose:
                    case["pass"] = 0
            contract += case.get("pass", 0)
            case["head"] = text[:120]
            rec["cases"].append(case)
            print(f"  {c['id']}: pass={case.get('pass')} schema={case.get('schema_ok','-')}", flush=True)
        except Exception as e:
            rec["cases"].append({"id": c["id"], "pass": 0, "error": str(e)[:150]})
    # nested tool args
    try:
        msg = lab.chat_nonstream(port, [{"role": "user", "content":
            "部署名为 api 的栈：3 副本，资源 cpu 1.5、内存 8GB，环境变量 LOG_LEVEL=debug 和 TZ=Asia/Shanghai。"}],
            extra={"tools": TOOL_NESTED, "tool_choice": "auto"}, max_tokens=400)
        calls = msg.get("tool_calls") or []
        tok = 0
        if calls:
            fn = calls[0].get("function", {})
            if fn.get("name") == "deploy_stack":
                a = json.loads(fn.get("arguments") or "{}")
                if a.get("name") == "api" and a.get("replicas") == 3 and a.get("resources", {}).get("mem_gb") == 8 \
                   and a.get("env", {}).get("TZ") == "Asia/Shanghai":
                    tok = 1
        rec["nested_tool_args"] = {"pass": tok, "raw": calls[:1]}
    except Exception as e:
        rec["nested_tool_args"] = {"pass": 0, "error": str(e)[:150]}
    rec["score"] = {"cases_pass": contract, "n": len(CASES), "json_valid": valid_json,
                    "nested_tool": rec["nested_tool_args"]["pass"]}
    rec["tps"] = lab.parse_tps(cname)
    (lab.EVID / "runs" / "structured-output").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "structured-output" / f"{key}.json", rec)
    lab.server_down(cname)
    print(json.dumps(rec["score"]))


if __name__ == "__main__":
    main()
