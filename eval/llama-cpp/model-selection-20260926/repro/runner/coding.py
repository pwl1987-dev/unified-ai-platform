"""coding.py — CODING-SUITE: multi-language tasks; executable verification is the authority.

python/bash/sql/c compile+run when toolchain available; dockerfile/compose/ci/git verified
structurally; code-review verified by expected-token match.
Usage: uv run python coding.py <image> <gpu> <model_path> <model_key> [ctx] [port]
Output: evidence runs/coding/<model_key>.json
"""
from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab


def run_py(code: str, tests: str) -> dict:
    p = subprocess.run([sys.executable, "-I", "-c", code + "\n" + tests], capture_output=True, text=True, timeout=90)
    return {"pass": 1 if p.returncode == 0 and "ALL_OK" in p.stdout else 0,
            "detail": (p.stdout + p.stderr).strip()[:280]}


def extract_code(r: dict) -> str | None:
    m = re.search(r"```(?:python|bash|sql|c|ts|typescript|javascript|yaml|yml|dockerfile|text)?\s*\n(.*?)```", r["text"], re.S)
    return m.group(1) if m else None


def task_python_merge(port):
    q = ("实现 merge_intervals(intervals: list[list[int]]) -> list[list[int]]：合并重叠区间，输入已按起点排序可假设不成立，"
         "结果按起点排序。只输出 ```python 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=1500, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        t = ("i=merge_intervals([[1,3],[2,6],[8,10],[15,18]]);assert i==[[1,6],[8,10],[15,18]],i;"
             "assert merge_intervals([[5,7],[1,3]])==[[1,3],[5,7]];assert merge_intervals([[1,4],[4,5]])==[[1,5]];"
             "print('ALL_OK')")
        res = run_py(code, t); ok, d = res["pass"], res["detail"]
    return {"id": "py_merge", "pass": ok, "detail": d, "wall_s": r["wall_s"], "reasoning_chars": r["reasoning_chars"], "usage": r.get("usage")}


def task_python_lru(port):
    q = ("实现类 LRUCache(capacity)：get(key) 不存在返回 -1；put(key,value) 淘汰最久未使用。O(1) 期望复杂度。"
         "只输出 ```python 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=1500, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        t = ("c=LRUCache(2);c.put(1,1);c.put(2,2);assert c.get(1)==1;c.put(3,3);assert c.get(2)==-1;"
             "c.put(4,4);assert c.get(1)==-1;assert c.get(3)==3;c.get(3);c.put(5,5);assert c.get(4)==-1;"
             "print('ALL_OK')")
        res = run_py(code, t); ok, d = res["pass"], res["detail"]
    return {"id": "py_lru", "pass": ok, "detail": d, "wall_s": r["wall_s"], "usage": r.get("usage")}


def task_python_bugfix(port):
    q = ("下面函数在 weights 含 0 时崩溃且语义错误（应返回加权平均，零权重跳过）。修复它。只输出修复后的完整函数，```python 块。\n"
         "def weighted_avg(values, weights):\n    return sum(v*w for v,w in zip(values,weights)) / sum(weights)")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=1200, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        t = ("import math\na=weighted_avg([1,2,3],[0,0,0])\nassert math.isnan(a) or a==0, a\n"
             "assert abs(weighted_avg([1,3],[0,2])-3)<1e-9\nassert abs(weighted_avg([2,4],[1,1])-3)<1e-9\nprint('ALL_OK')")
        res = run_py(code, t); ok, d = res["pass"], res["detail"]
    return {"id": "py_bugfix", "pass": ok, "detail": d, "wall_s": r["wall_s"]}


def task_bash_topdir(port):
    q = ("写一个 bash 脚本：从 stdin 读 du -k 输出（两列 KB 和路径），输出占用最大的前 3 个目录，格式 'KB path'。"
         "只输出 ```bash 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=900, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        fixture = "120\ta/b\n500\tx\n30\tz\n900\tq\n700\tm\n"
        p = subprocess.run(["bash", "-c", code], input=fixture, capture_output=True, text=True, timeout=30)
        lines = [l.strip() for l in p.stdout.strip().splitlines() if l.strip()]
        first = lines[0] if lines else ""
        ok = 1 if p.returncode == 0 and first.startswith("900") and len(lines) >= 3 else 0
        d = p.stdout.strip()[:150] + " | " + p.stderr.strip()[:100]
    return {"id": "bash_top3", "pass": ok, "detail": d, "wall_s": r["wall_s"]}


def task_sql_monthly(port):
    q = ("表 orders(id INT, cust TEXT, amt REAL, created TEXT 'YYYY-MM-DD')。写一条 SQLite SQL："
         "返回每个月的总收入 amt 和订单数，按月份升序。只输出 ```sql 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=800, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        setup = ("CREATE TABLE orders(id INT, cust TEXT, amt REAL, created TEXT);"
                 "INSERT INTO orders VALUES (1,'a',10.0,'2026-01-05'),(2,'b',5.0,'2026-01-20'),(3,'a',7.0,'2026-02-01'),"
                 "(4,'c',20.0,'2026-02-15'),(5,'c',3.0,'2026-03-09');")
        p = subprocess.run(["sqlite3", ":memory:", setup + " " + code + ";"], capture_output=True, text=True, timeout=30)
        expected = "15.0|2\n27.0|2\n3.0|1"
        ok = 1 if expected.replace(" ", "") in p.stdout.replace(" ", "").replace("\r", "") else 0
        d = p.stdout.strip()[:150] + " | " + p.stderr.strip()[:100]
    return {"id": "sql_monthly", "pass": ok, "detail": d, "wall_s": r["wall_s"]}


def task_dockerfile(port):
    q = ("写一个多阶段 Dockerfile：阶段1用 python:3.12-slim 装 requirements.txt 并构建；阶段2同基础镜像，"
         "仅 COPY --from=构建产物，用非 root 用户 app 运行 app.py。只输出 ```dockerfile 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=900, temperature=0.0, seed=42)
    code = extract_code(r) or r["text"]
    ok = 1 if (len(re.findall(r"^FROM", code, re.M)) >= 2 and "COPY --from" in code
               and re.search(r"USER\s+app", code)) else 0
    return {"id": "dockerfile_multistage", "pass": ok, "detail": code[:200], "wall_s": r["wall_s"]}


def task_compose_health(port):
    q = ("写 docker-compose.yml 片段：服务 web 用 nginx:alpine，端口 8080:80，带 healthcheck（wget /health，间隔 30s，"
         "超时 5s，重试 3 次），restart: unless-stopped。只输出 ```yaml 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=800, temperature=0.0, seed=42)
    code = extract_code(r) or r["text"]
    ok = 1 if ("8080:80" in code and "healthcheck" in code and "30s" in code and "unless-stopped" in code) else 0
    return {"id": "compose_healthcheck", "pass": ok, "detail": code[:200], "wall_s": r["wall_s"]}


def task_git_soft(port):
    q = ("Git：如何撤销最近一次 commit 但保留全部改动在暂存区？给出完整命令。只输出命令。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=400, temperature=0.0, seed=42)
    ok = 1 if re.search(r"git reset --soft HEAD~1", r["text"]) else 0
    return {"id": "git_soft_reset", "pass": ok, "detail": r["text"][:100], "wall_s": r["wall_s"]}


def task_review_div0(port):
    q = ("Code review 以下 diff，指出唯一的实质性 bug（格式：'BUG: <描述>'）：\n"
         "```diff\n-def avg(xs): return sum(xs)/len(xs)\n+def avg(xs):\n+    if len(xs) == 0:\n+        return 0\n"
         "+    n = len(xs) - 1\n+    return sum(xs) / n\n```")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=800, temperature=0.0, seed=42)
    ok = 1 if re.search(r"BUG[:：]", r["text"]) and ("len(xs) - 1" in r["text"] or "n = len" in r["text"] or "分母" in r["text"]) else 0
    return {"id": "review_div0", "pass": ok, "detail": r["text"][:150], "wall_s": r["wall_s"]}


def task_ts_debounce(port):
    q = ("写 TypeScript 函数 debounce<F extends (...args:any[])=>void>(fn: F, ms: number)：返回防抖包装，"
         "带 cancel() 方法。只输出 ```typescript 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=900, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        bal = code.count("{") - code.count("}")
        ok = 1 if ("setTimeout" in code and bal == 0 and "cancel" in code) else 0
        d = f"braces_bal={bal}"
    return {"id": "ts_debounce", "pass": ok, "detail": d, "wall_s": r["wall_s"], "note": "structural check (no node on host)"}


def task_c_reverse(port):
    q = ("写 C 函数 void reverse_in_place(char *s)：原地反转字符串，不分配新缓冲区，处理 NULL。"
         "只输出 ```c 代码块（含 #include 需要的头）。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=800, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        prog = code + "\nint main(){char b[16];strcpy(b,\"abcdef\");reverse_in_place(b);"
        prog += "printf(\"%s\",b);reverse_in_place(NULL);printf(\"|ok\");return 0;}"
        p = subprocess.run(["bash", "-c", f"cat >/tmp/lc_c_{int(time.time())}.c <<'XEOF'\n{prog}\nXEOF\ngcc -o /tmp/lc_c_out ${{REPLY:-/tmp/lc_c_*.c}} 2>/dev/null; gcc /tmp/lc_c_*.c -o /tmp/lc_c_out && /tmp/lc_c_out"],
                           capture_output=True, text=True, timeout=60)
        ok = 1 if "fedcba|ok" in p.stdout else 0
        d = (p.stdout + p.stderr).strip()[:200]
    return {"id": "c_reverse", "pass": ok, "detail": d, "wall_s": r["wall_s"], "note": "gcc host compile"}


def task_ci_workflow(port):
    q = ("写 GitHub Actions workflow（YAML）：push 到 main 时跑两个 job——lint（ubuntu-latest, 运行 flake8）和"
         " test（ubuntu-latest, python 3.12, pip install -r requirements.txt 后 pytest）。只输出 ```yaml 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=900, temperature=0.0, seed=42)
    code = extract_code(r) or r["text"]
    ok = 1 if ("on:" in code and "jobs:" in code and "lint" in code and "test" in code
               and "pytest" in code and "flake8" in code and "3.12" in code) else 0
    return {"id": "ci_workflow", "pass": ok, "detail": "structural", "wall_s": r["wall_s"]}


def task_regex_log(port):
    q = ("写 Python 正则提取 nginx 日志 '1.2.3.4 - - [26/Sep/2026:08:00:01 +0800] \"GET /a HTTP/1.1\" 200 512' 中的"
         " IP、路径、状态码，返回 tuple(ip, path, status)。只输出 ```python 代码块。")
    r = lab.chat(port, [{"role": "user", "content": q}], max_tokens=900, temperature=0.0, seed=42)
    code = extract_code(r)
    ok, d = 0, "no block"
    if code:
        t = ("m=parse('1.2.3.4 - - [26/Sep/2026:08:00:01 +0800] \"GET /a HTTP/1.1\" 200 512');"
             "assert m==('1.2.3.4','/a','200'),m;print('ALL_OK')")
        res = run_py(code, t); ok, d = res["pass"], res["detail"]
    return {"id": "py_regex_log", "pass": ok, "detail": d, "wall_s": r["wall_s"]}


TASKS = [task_python_merge, task_python_lru, task_python_bugfix, task_regex_log, task_bash_topdir,
         task_sql_monthly, task_dockerfile, task_compose_health, task_git_soft, task_review_div0,
         task_ts_debounce, task_c_reverse, task_ci_workflow]


def main():
    image, gpu, model_path, key = sys.argv[1:5]
    ctx = int(sys.argv[5]) if len(sys.argv) > 5 else 32768
    port = int(sys.argv[6]) if len(sys.argv) > 6 else 18151
    cname = f"coding-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c {ctx} -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a coding "
           f"-b 512 -ub 512 --metrics")
    rec = {"model": key, "image": image, "ctx": ctx, "tasks": []}
    lab.server_up(cname, image, port, gpu, cmd)
    rec["vram_after_load"] = lab.vram_mib(gpu)
    time.sleep(2)
    for attempt in range(3):
        try:
            lab.chat_nonstream(port, [{"role": "user", "content": "ping"}], max_tokens=16)
            break
        except Exception:
            time.sleep(3)
    for t in TASKS:
        try:
            res = t(port)
        except Exception as e:
            res = {"id": getattr(t, "__name__", "?"), "pass": 0, "error": str(e)[:200]}
        rec["tasks"].append(res)
        print(f"  {res['id']}: pass={res['pass']}", flush=True)
    rec["score"] = sum(t["pass"] for t in rec["tasks"])
    rec["tps"] = lab.parse_tps(cname)
    rec["vram_peak"] = lab.vram_mib(gpu)
    (lab.EVID / "runs" / "coding").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "coding" / f"{key}.json", rec)
    lab.server_down(cname)
    print(f"SCORE {rec['score']}/{len(rec['tasks'])}")


if __name__ == "__main__":
    main()
