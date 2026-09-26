"""writing.py — CHINESE-WRITING-SUITE: machine metrics (facts kept / no fabrication /
length adherence / structure / repetition / terminology), texts archived for human spot review.
Usage: uv run python writing.py <image> <gpu> <model_path> <model_key> [port]
"""
from __future__ import annotations
import json, re, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab

SRC = ("背景材料：我司融媒体平台 2026Q3 完成 GPU 推理集群扩容（8×RTX4090），上线了自动拆条与字幕服务，"
       "视频处理时效从 45 分钟降到 6 分钟；新签两家地市电视台；季度营收 1180 万元，同比 +23%；"
       "尚存问题：夜间批次失败率 1.8%，原因集中在素材源不稳定。")

TASKS = [
    {"id": "tech_plan", "prompt": "以'运维值班系统改造方案'为题写一节技术方案（300字左右）：目标、现状、改造点（含灰度与回滚）。", "target_chars": (220, 480),
     "must": ["灰度", "回滚"], "must_not": ["1180万", "23%"], "structure": ["目标", "现状"]},
    {"id": "project_readme", "prompt": "为一个名为 media-pipeline 的 Python 项目写 README 简介（250字左右）：功能、安装、用法、许可。", "target_chars": (180, 400),
     "must": ["media-pipeline", "安装"], "must_not": ["1180万"], "structure": ["##"]},
    {"id": "work_summary", "prompt": f"根据以下材料写 150 字工作总结：{SRC}", "target_chars": (100, 260),
     "must": ["8", "45", "6"], "must_not": ["失败率 0%"], "structure": []},
    {"id": "tech_report", "prompt": f"把材料改写成对管理层的技术汇报（200字，先结论后论据）：{SRC}", "target_chars": (140, 340),
     "must": ["6 分钟", "23%"], "must_not": ["扩容到16卡", "32卡"], "structure": []},
    {"id": "news_style", "prompt": f"用融媒新闻稿口吻改写材料（180字，客观、不加未提及数据）：{SRC}", "target_chars": (120, 300),
     "must": ["电视台"], "must_not": [" miraculous ", "全球领先"], "structure": []},
    {"id": "localize", "prompt": "把下面英文段落中文化，术语准确，不增删信息：'The KV cache is quantized to 4 bits per weight, reducing VRAM footprint by 62% while keeping perplexity within 0.3%.'",
     "target_chars": (40, 160), "must": ["KV", "显存"], "must_not": ["8比特", "8 位"], "structure": []},
    {"id": "explain", "prompt": "向非技术同事解释'为什么大模型推理贵'（150字，用比喻，不用公式）。", "target_chars": (100, 260),
     "must": [], "must_not": ["dF/dx"], "structure": []},
    {"id": "rewrite_formal", "prompt": "把口语改写成正式书面语，意思不变：'这个 bug 挺离谱的，一查原来是缓存没清，清了就好了。'（80字内）", "target_chars": (30, 110),
     "must": ["缓存"], "must_not": ["离谱"], "structure": []},
    {"id": "compress", "prompt": f"把材料压缩成 60 字以内的单句：{SRC}", "target_chars": (20, 75), "must": ["6 分钟"],
     "must_not": ["1.8%"], "structure": []},
    {"id": "expand", "prompt": f"基于材料中'时效从45分钟到6分钟'这一点扩写 200 字的技术侧分析（为什么能提速），不得编造具体新数字。",
     "target_chars": (140, 340), "must": ["45", "6"], "must_not": ["提速了 97.3%"], "structure": []},
    {"id": "multi_source", "prompt": "综合两段材料写 120 字结论。材料A：{SRC}；材料B：竞品同期发布自动剪辑功能，定价为我们 1.5 倍。",
     "target_chars": (80, 220), "must": ["竞品"], "must_not": ["我们降价"], "structure": []},
    {"id": "long_summary_structured", "prompt": f"把材料扩为结构化报告（300字）：一、总体进展；二、数据亮点；三、风险与对策。{SRC}",
     "target_chars": (220, 480), "must": ["一、", "二、", "三、", "1.8%"], "must_not": [], "structure": ["一、", "二、", "三、"]},
]


def repetition_score(t: str) -> int:
    for i in range(0, max(len(t) - 16, 0), 8):
        w = t[i:i + 16]
        if len(w) == 16 and t.count(w) >= 3:
            return 1
    return 0


def evaluate(task: dict, text: str) -> dict:
    n = len(text)
    lo, hi = task["target_chars"]
    facts = sum(1 for m in task["must"] if m in text)
    fabric = [m for m in task["must_not"] if m in text]
    struct = sum(1 for s in task["structure"] if s in text)
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    rep = repetition_score(text)
    ok = 1 if (lo <= n <= hi and facts == len(task["must"]) and not fabric
               and struct == len(task["structure"]) and rep == 0 and zh > n * 0.3) else 0
    return {"pass": ok, "chars": n, "in_range": 1 if lo <= n <= hi else 0,
            "facts": f"{facts}/{len(task['must'])}", "fabrications": fabric, "structure_ok": f"{struct}/{len(task['structure'])}",
            "repetition_loop": rep, "zh_ratio": round(zh / max(n, 1), 2)}


def main():
    image, gpu, model_path, key = sys.argv[1:5]
    port = int(sys.argv[5]) if len(sys.argv) > 5 else 18181
    cname = f"writing-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c 32768 -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a writing -b 512 -ub 512 --metrics")
    rec = {"model": key, "tasks": [], "human_review_pending": True}
    lab.server_up(cname, image, port, gpu, cmd)
    time.sleep(2)
    for attempt in range(3):
        try:
            lab.chat_nonstream(port, [{"role": "user", "content": "ping"}], max_tokens=16)
            break
        except Exception:
            time.sleep(3)
    for t in TASKS:
        try:
            r = lab.chat(port, [{"role": "user", "content": t["prompt"]}], max_tokens=1600,
                         temperature=0.0, seed=42, extra={"chat_template_kwargs": {"enable_thinking": False}})
            ev = evaluate(t, r["text"])
            ev.update({"id": t["id"], "wall_s": r["wall_s"], "text": r["text"][:600]})
        except Exception as e:
            ev = {"id": t["id"], "pass": 0, "error": str(e)[:150]}
        rec["tasks"].append(ev)
        print(f"  {t['id']}: pass={ev.get('pass')} chars={ev.get('chars')}", flush=True)
    rec["score"] = sum(t.get("pass", 0) for t in rec["tasks"])
    rec["tps"] = lab.parse_tps(cname)
    (lab.EVID / "runs" / "writing").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "writing" / f"{key}.json", rec)
    lab.server_down(cname)
    print(f"WRITING SCORE {rec['score']}/{len(rec['tasks'])}")


if __name__ == "__main__":
    main()
