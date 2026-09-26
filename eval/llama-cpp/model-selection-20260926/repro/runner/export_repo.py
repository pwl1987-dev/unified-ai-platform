#!/usr/bin/env python3
"""export_repo.py — sanitized evidence export to the public repo.

Applies the 8-rule substitution table from lab/AGENTS.md (plaintext only lives
on the host; the public repo must never see it), copies capped-size evidence,
and prints a pre-commit scan. Run AFTER summarize.py.
"""
from __future__ import annotations
import json, re, shutil, sys
from pathlib import Path

SRC = Path("/data/tasks/qwen-model-lab/benchmarks/llama-cpp/model-selection-2026-09")
DST = Path("/data/repos/qwen3.8-27b-8x4090-stack/eval/llama-cpp/model-selection-20260926")
OPS = Path("/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab")

SUBS = [
    ("<已脱敏>", "<已脱敏>"),
    ("api.<内网域名>", "api.<内网域名>"),
    ("cms.<内网域名>", "cms.<内网域名>"),
    ("files.<内网域名>", "files.<内网域名>"),
    ("stream.<内网域名>", "stream.<内网域名>"),
    ("<内部账号>", "<内部账号>"),
    ("<已脱敏>", "<已脱敏>"),
    ("127.0.0.1", "127.0.0.1"),
    ("127.0.0.2", "127.0.0.2"),
]

FILES_TEXT = [
    "environment.json", "control-prod.json", "runtime-matrix.json", "runtime-selection.json",
    "artifact-matrix.json", "model-profiles.json", "summary.json", "pareto.json", "swift15-normal-sha256.txt",
    "licenses/LICENSE-GATE.md", "licenses/swift-open-license-1.0.txt",
    "CONTROL-PROD-REALITY.md", "control-prod-props.json",
    "README.md", "PRODUCTION-RECOMMENDATION.md",
]
DIRS_JSON = ["runs/runtime-ab", "runs/stage1", "runs/longctx", "runs/long-code", "runs/coding",
             "runs/structured-output", "runs/agent", "runs/writing", "runs/vision", "runs/opt",
             "runs/concurrency", "runs/gpu"]
OPS_FILES = ["docker-compose.yml", "build-sm89.sh", "download-stage1.sh", "battery.sh", "scale_queue.sh",
             "build/Dockerfile.sm89", "build/BUILD-SHA.txt"]
OPS_RUNNER = ["lab.py", "runtime_ab.py", "screening.py", "needle.py", "longcode.py", "coding.py",
              "structured.py", "agent.py", "writing.py", "vision.py", "opt_ab.py", "concurrency.py",
              "gpu_scale.py", "soak_smoke.py", "soak_plain.py", "summarize.py", "parse_runtime_logs.py",
              "export_repo.py", "pyproject.toml", "uv.lock"]

MAX_BYTES = 2_000_000
BAN = re.compile(r"d@f%s\^x&|api\.lytv\.tv|msadmin\.lytv\.tv|file\.lytv\.tv|m3u8-channel\.lytv\.tv|<内部账号>|<已脱敏>|10\.30\.51\.13|10\.30\.51\.12")


def sanitize(text: str) -> str:
    for a, b in SUBS:
        text = text.replace(a, b)
    return text


def copy_sanitized(src: Path, dst: Path, cap: int = MAX_BYTES, binary: bool = False) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        if src.stat().st_size > 20_000_000:
            return False
        shutil.copy2(src, dst)
        return True
    data = src.read_text(errors="replace")
    if len(data.encode()) > cap:
        data = data[:cap] + "\n<!-- truncated by exporter (2MB cap) -->"
    dst.write_text(sanitize(data))
    return True


def main():
    n = 0
    for f in FILES_TEXT:
        n += copy_sanitized(SRC / f, DST / f)
    for d in DIRS_JSON:
        for f in sorted((SRC / d).glob("*.json")):
            n += copy_sanitized(f, DST / d / f.name)
        for f in sorted((SRC / d).glob("*.txt")):
            if f.stat().st_size <= 400_000:
                n += copy_sanitized(f, DST / d / f.name)
    for f in OPS_FILES:
        n += copy_sanitized(OPS / f, DST / "repro" / Path(f).name)
    for f in OPS_RUNNER:
        n += copy_sanitized(OPS / "runner" / f, DST / "repro" / "runner" / f)
    print(f"exported {n} files -> {DST}")
    # pre-commit scan on the whole repo
    bad = []
    for p in DST.rglob("*"):
        if p.is_file():
            try:
                hit = BAN.search(p.read_text(errors="ignore"))
            except Exception:
                continue
            if hit:
                bad.append((str(p), hit.group(0)))
    if bad:
        print("SANITIZE FAIL:")
        for b in bad[:20]:
            print(" ", b)
        sys.exit(1)
    print("sanitize scan: CLEAN")


if __name__ == "__main__":
    main()
