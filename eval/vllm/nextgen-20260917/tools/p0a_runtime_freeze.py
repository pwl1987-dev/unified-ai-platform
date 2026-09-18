#!/usr/bin/env python3
"""P0A.2 — runtime029_phase02_baseline 终态快照（Phase 02 v1.2 计划）。

Phase 01 期间环境实际变过（a/b/c/e 补丁落树、pandas/pyarrow 补装），MANIFEST 的
tree sha 45c5c919… 是打补丁前基准。本脚本冻结 Phase 02 的可验证起点：
  - 完整包清单（pip freeze）+ 关键包版本
  - patched source tree hash（site-packages/vllm 打补丁后重算）
  - patch-units/*.patch 文件 SHA256 + patched-files-ledger 一致性核对
    （当前文件 sha 必须与 Phase 01 台账 sha256_after 一致，否则 ENV_DRIFT）
  - sys.path 优先级 + patched-symbol provenance（import→getfile→SHA 链）
输出 repro/env029/runtime029-phase02-baseline.json；退出码非 0 = 存在漂移。
"""
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path

ENV = Path("/data/tools/vllm29-env")
REPRO = Path("/file-not-used")  # placeholder, set in main
KEY_PKGS = ["vllm", "torch", "transformers", "flashinfer-python", "triton",
            "pandas", "pyarrow", "nccl", "cuda-runtime", "xformers"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root: Path) -> tuple[str, int]:
    """排序相对路径 + 内容的聚合哈希（只收 .py/.so；排除 __pycache__）。"""
    h = hashlib.sha256()
    n = 0
    for p in sorted(root.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts:
            continue
        if p.suffix not in (".py", ".so", ".pyi"):
            continue
        rel = str(p.relative_to(root))
        h.update(rel.encode())
        h.update(b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
        n += 1
    return h.hexdigest(), n


def main() -> int:
    repo = Path(__file__).resolve().parents[1]          # .../nextgen-20260917
    env_dir = repo / "repro" / "env029"
    out_path = env_dir / "runtime029-phase02-baseline.json"

    venv_py = ENV / "bin" / "python"
    if not venv_py.exists():
        print(f"FATAL: venv python missing: {venv_py}", file=sys.stderr)
        return 2

    report: dict = {
        "purpose": "runtime029_phase02_baseline——Phase 02 只读起点（打补丁+补装后终态）",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "env": str(ENV),
        "python_version": subprocess.run([str(venv_py), "-V"], capture_output=True,
                                         text=True).stdout.strip(),
    }

    # 1) pip freeze 终态
    frz = subprocess.run([str(venv_py), "-m", "pip", "freeze", "--all"],
                         capture_output=True, text=True)
    (env_dir / "freeze-phase02-baseline.txt").write_text(frz.stdout)
    report["pip_freeze_file"] = "freeze-phase02-baseline.txt"
    report["pip_freeze_sha256"] = sha256_file(env_dir / "freeze-phase02-baseline.txt")

    # 2) 关键包版本（importlib.metadata，venv 解释器内查）
    ver_script = (
        "import importlib.metadata as m, json;"
        "out={};"
        + "".join(
            f"out[{k!r}]=(lambda s: s)(m.version({k!r})) if True else None;"
            for k in KEY_PKGS)
        + "print(json.dumps(out))")
    # 上面生成器对缺失包会抛异常，改用安全版：
    ver_script = (
        "import importlib.metadata as m, json\n"
        "out={}\n"
        "for k in %r:\n"
        "    try: out[k]=m.version(k)\n"
        "    except Exception: out[k]=None\n"
        "print(json.dumps(out))\n" % (KEY_PKGS,))
    vr = subprocess.run([str(venv_py), "-c", ver_script], capture_output=True, text=True)
    report["package_versions"] = json.loads(vr.stdout)
    tvr = subprocess.run([str(venv_py), "-c",
                          "import torch; print(torch.version.cuda)"],
                         capture_output=True, text=True)
    report["torch_cuda"] = tvr.stdout.strip()

    # 3) patched vllm tree hash（site-packages/vllm）
    site = subprocess.run([str(venv_py), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True).stdout.strip()
    vllm_root = Path(site) / "vllm"
    th, nfiles = tree_hash(vllm_root)
    report["vllm_tree"] = {
        "root": str(vllm_root),
        "files_hashed": nfiles,
        "sha256_post_patch": th,
        "note": "打补丁后终态；与 phase01.baseline_tree_sha256_pre_patch(45c5c919…) 不同属预期",
    }

    # 4) patch 文件 SHA + 台账一致性核对（当前文件 sha vs Phase 01 sha256_after）
    patches = {}
    for p in sorted((env_dir / "patch-units").glob("*.patch")):
        patches[p.name] = sha256_file(p)
    report["patch_unit_files_sha256"] = patches

    ledger = json.loads((env_dir / "patched-files-ledger.json").read_text())
    drift = []
    verified = []
    for ent in ledger.get("patches", []):
        f = ent.get("file")
        if not f or ent.get("status", "").startswith("PORTED_BUT_INERT") and not f:
            continue
        if not f:
            continue
        cur = vllm_root / f
        if not cur.exists():
            # unit-d 新增文件没有 file 字段或为相对路径差异，单独记录
            drift.append({"file": f, "issue": "MISSING_ON_DISK"})
            continue
        cur_sha = sha256_file(cur)
        want = ent.get("sha256_after", "").replace("-truncated", "")
        ok = (cur_sha == want) if want else None
        verified.append({"file": f, "match_with_phase01_ledger": ok,
                         "sha256_now": cur_sha})
        if ok is False:
            drift.append({"file": f, "issue": "SHA_DRIFT",
                          "phase01_after": want, "now": cur_sha})
    report["patched_file_integrity"] = {
        "checked": verified, "drift": drift,
        "verdict": "CLEAN" if not drift else "ENV_DRIFT",
    }

    # 5) sys.path 优先级 + patched-symbol provenance
    prov_script = r"""
import inspect, json, hashlib, sys
syms = {
 "qwen3_5": "vllm.model_executor.models.qwen3_5",
 "qwen3_5_mtp": "vllm.model_executor.models.qwen3_5_mtp",
 "logits_processor": "vllm.model_executor.layers.logits_processor",
 "kv_cache_utils": "vllm.v1.core.kv_cache_utils",
 "attention_registry": "vllm.v1.attention.backends.registry",
 "platforms_cuda": "vllm.platforms.cuda",
}
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()
out = {"sys_path": sys.path, "overlay_in_path": [p for p in sys.path if "overlay" in p], "symbols": {}}
for k, mod in syms.items():
    try:
        m = __import__(mod, fromlist=["x"])
        fp = inspect.getfile(m)
        out["symbols"][k] = {"module": mod, "file": fp, "sha256": sha(fp)}
    except Exception as e:
        out["symbols"][k] = {"module": mod, "error": repr(e)}
print(json.dumps(out))
"""
    pr = subprocess.run([str(venv_py), "-c", prov_script], capture_output=True,
                        text=True, env={"PATH": "/usr/bin:/bin",
                                        "HOME": str(Path.home()),
                                        "VLLM_DFLASH2_TORCH_TOPK": "1"})
    if pr.returncode != 0:
        report["provenance_error"] = pr.stderr[-2000:]
    else:
        report["symbol_provenance"] = json.loads(pr.stdout)

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(f"[freeze] wrote {out_path}")
    print(f"[freeze] vllm tree(post-patch) sha256 = {th} ({nfiles} files)")
    print(f"[freeze] integrity verdict = {report['patched_file_integrity']['verdict']}")
    return 0 if not drift else 1


if __name__ == "__main__":
    raise SystemExit(main())
