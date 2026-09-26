"""vision.py — VISION-CPU vs VISION-GPU A/B for a model+mmproj pair.
Deterministic generated business-style images (terminal screenshot / table / diagram),
OpenAI image_url base64 input, machine-scored by expected substrings.
Usage: uv run python vision.py <image> <gpu> <model_path> <mmproj> <model_key> <cpu|gpu> [port]
"""
from __future__ import annotations
import base64, io, json, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab


def img_terminal() -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (640, 240), (12, 12, 12))
    d = ImageDraw.Draw(im)
    d.text((12, 10), "$ llama-server --version", fill=(240, 240, 240))
    d.text((12, 34), "version: 0.3.0-dev (build 10715)", fill=(120, 220, 120))
    d.text((12, 58), "CUDA devices: 1  compute 8.9", fill=(200, 200, 200))
    d.text((12, 82), "ERROR: port 8080 already in use", fill=(240, 90, 90))
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def img_table() -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (560, 220), (255, 255, 255))
    d = ImageDraw.Draw(im)
    rows = [("service", "port", "state"), ("qwen27b", "8081", "RUNNING"),
            ("qwen27b-lb", "8000", "RUNNING"), ("qwen27b-mon", "9000", "STOPPED")]
    y = 12
    for r in rows:
        d.text((16, y), "  |  ".join(r), fill=(20, 20, 20))
        y += 40
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def img_flow() -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (620, 200), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 70, 150, 120], outline=(0, 0, 0), width=2)
    d.text((45, 85), "Client", fill=(0, 0, 0))
    d.arrow = None
    d.line([150, 95, 280, 95], fill=(0, 0, 0), width=2)
    d.polygon([(280, 88), (300, 95), (280, 102)], fill=(0, 0, 0))
    d.text((190, 65), "HTTP", fill=(0, 0, 0))
    d.rectangle([300, 70, 430, 120], outline=(0, 0, 0), width=2)
    d.text((312, 85), "OpenResty", fill=(0, 0, 0))
    d.line([430, 95, 560, 95], fill=(0, 0, 0), width=2)
    d.polygon([(560, 88), (580, 95), (560, 102)], fill=(0, 0, 0))
    d.rectangle([450, 30, 580, 60], outline=(0, 0, 0), width=2)
    d.text((465, 40), "llama.cpp x2", fill=(0, 0, 0))
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


CASES = [
    {"id": "terminal_shot", "img": img_terminal, "q": "这张终端截图里有几行内容？其中 ERROR 那一行说了什么？",
     "need": ["8080"],},
    {"id": "table_shot", "img": img_table, "q": "表里哪个服务是 STOPPED 状态？它的端口是多少？",
     "need": ["9000"]},
    {"id": "flow_diagram", "img": img_flow, "q": "架构图里请求从 Client 出发依次经过什么组件？最终到几个 llama.cpp 实例？",
     "need": ["2"]},
]


def b64(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def main():
    image, gpu, model_path, mmproj, key, mode = sys.argv[1:7]
    port = int(sys.argv[7]) if len(sys.argv) > 7 else 18191
    dev = "--mmproj-device none --no-mmproj-offload" if mode == "cpu" else ""
    cname = f"vision-{key}-{mode}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c 32768 -np 1 -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a vision "
           f"--mmproj {mmproj} {dev} -b 512 -ub 512 --metrics")
    rec = {"model": key, "mmproj_mode": mode, "cases": []}
    lab.server_up(cname, image, port, gpu, cmd)
    time.sleep(2)
    for c in CASES:
        data = c["img"]()
        t0 = time.time()
        try:
            r = lab.chat(port, [{"role": "user", "content": [
                {"type": "text", "text": c["q"]},
                {"type": "image_url", "image_url": {"url": b64(data)}}]}],
                max_tokens=600, temperature=0.0, seed=42)
            ok = 1 if all(n in r["text"] for n in c["need"]) else 0
            rec["cases"].append({"id": c["id"], "pass": ok, "ttft_s": r["ttft_s"], "wall_s": r["wall_s"],
                                 "img_kb": round(len(data) / 1024, 1), "answer_head": r["text"][:120]})
            print(f"  {c['id']}: pass={ok} ttft={r['ttft_s']} wall={r['wall_s']}", flush=True)
        except Exception as e:
            rec["cases"].append({"id": c["id"], "pass": 0, "error": str(e)[:200]})
    rec["vram_after_load"] = lab.vram_mib(gpu)
    rec["ram_note"] = "mmproj on CPU keeps VRAM for LM+KV; RSS impact visible in docker stats"
    st = lab.sh(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", cname]).stdout.strip()
    rec["container_mem"] = st
    (lab.EVID / "runs" / "vision").mkdir(parents=True, exist_ok=True)
    lab.write_json(lab.EVID / "runs" / "vision" / f"{key}-{mode}.json", rec)
    lab.server_down(cname)
    print(json.dumps({"mode": mode, "score": sum(c["pass"] for c in rec["cases"]),
                      "vram": rec["vram_after_load"]["vram_used_mib"], "mem": st}, ensure_ascii=False))


if __name__ == "__main__":
    main()
