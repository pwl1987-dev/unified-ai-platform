#!/usr/bin/env python3
"""P0A.1（Phase 03 v1.1 契约）— runtime029 环境冻结，fail-closed 重写版。

Phase 02 版 bug（勘误 EP03-A1）：`python -m pip freeze --all` 在 uv venv（无 pip）
下 rc!=0、stdout 空；旧工具不查 returncode 即写出 0 字节 freeze 文件
（sha256=e3b0c442…），并继续生成 CLEAN baseline——fail-open 取证缺陷。

本版契约（gates-phase03.yaml A1，Phase 03 v1.1 用户修正 #1）：
  1. 双路包清单：`uv pip freeze --python <venv>`（主）+ importlib.metadata 枚举
     （独立交叉验证）。不要求两份原始文本逐字一致——按 PEP 503 规范化后比对
     name→version；editable / direct-url / local-build 单独记 provenance。
  2. 任一 inventory 命令 rc!=0 / stderr 示败 / stdout 空 / 包数低于下限 → FATAL
     （退出码 2），绝不写出空 freeze 后继续。
  3. 关键包必须在两路都存在、版本一致，并与 Phase 02 认证基线一致。
  4. freeze 文件写入 = temp → 全部校验通过 → atomic rename；校验未过禁止覆盖。
  5. 与 Phase 02 已认证基线（vllm tree sha / patch unit sha / 台账 sha_after /
     symbol provenance sha / 关键包版本）零漂移 → EVIDENCE_REPAIR（仅包清单取证
     bug 被修复）；任何不符 → ENV_DRIFT（退出码 1）。
  6. vllm29-env 只读：本工具绝不向其安装任何包（无 pip 也不装 pip）。
     新产物：runtime029-phase03-inheritance.json（本工具输出，不改写 Phase 02
     认证基线 JSON 本身）。
"""
import hashlib
import inspect  # noqa: F401  (provenance 子脚本内使用)
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ENV = Path("/data/tools/vllm29-env")
REPO = Path(__file__).resolve().parents[1]          # .../nextgen-20260917
ENVDIR = REPO / "repro" / "env029"
BASELINE = ENVDIR / "runtime029-phase02-baseline.json"
FREEZE = ENVDIR / "freeze-phase02-baseline.txt"
IMPLIB_RAW = ENVDIR / "inventory-importlib-phase03.json"
INHERIT = ENVDIR / "runtime029-phase03-inheritance.json"

MIN_PKGS = 150          # 实测 199；低于此=清单异常，FATAL
KEY_PKGS = ["vllm", "torch", "transformers", "flashinfer-python",
            "triton", "pandas", "pyarrow"]

_PEP503 = re.compile(r"[-_.]+")


def norm(name: str) -> str:
    return _PEP503.sub("-", name.strip()).lower()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root: Path) -> tuple[str, int]:
    """排序相对路径 + 内容的聚合哈希（只收 .py/.so/.pyi；排除 __pycache__）。"""
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


def fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run(cmd: list[str], *, what: str, env: dict | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        fatal(f"{what} rc={r.returncode} cmd={' '.join(cmd)} stderr={r.stderr[-500:]}")
    return r


# ---------------------------------------------------------------- inventory
def parse_uv_freeze(text: str) -> tuple[dict, list, list]:
    """返回 (norm(name)→version, editable 记录, direct-url 记录)。"""
    vers: dict[str, str] = {}
    editable, direct = [], []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.startswith("-e ") or " @ file://" in ln or " @ " in ln:
            # uv/pip 的 editable/direct-url 形态：-e name @ url / name @ url
            body = ln[3:] if ln.startswith("-e ") else ln
            name = body.split(" @ ")[0].split("==")[0].strip()
            (editable if ln.startswith("-e ") else direct).append(
                {"raw": ln, "name": name, "norm": norm(name)})
            continue
        if "==" in ln:
            n, v = ln.split("==", 1)
            vers[norm(n)] = v.strip()
        else:  # 无版本条目（罕见）——按 provenance 记，不进版本表
            direct.append({"raw": ln, "name": ln, "norm": norm(ln)})
    return vers, editable, direct


IMPLIB_SCRIPT = r"""
import importlib.metadata as m, json
out = []
for d in m.distributions():
    du = None
    try:
        du = (d.read_text("direct_url.json") or "").strip() or None
    except Exception:
        pass
    out.append({"name": d.name, "version": d.version,
                "direct_url_json": du,
                "local_file": bool(du and '"file://"' in du)})
print(json.dumps(out))
"""


def main() -> int:
    venv_py = ENV / "bin" / "python"
    if not venv_py.exists():
        fatal(f"venv python missing: {venv_py}")
    uv = shutil.which("uv")
    if not uv:
        fatal("uv not found on PATH")
    if not BASELINE.exists():
        fatal(f"Phase 02 certified baseline missing: {BASELINE}")
    baseline = json.loads(BASELINE.read_text())

    # 旧 freeze 取证（覆盖前记录）
    old_freeze = {"path": str(FREEZE)}
    if FREEZE.exists():
        old_freeze["size_bytes"] = FREEZE.stat().st_size
        old_freeze["sha256_before_repair"] = sha256_file(FREEZE)
    else:
        old_freeze["size_bytes"] = None
        old_freeze["sha256_before_repair"] = None

    uv_ver = run([uv, "--version"], what="uv --version").stdout.strip()

    # ---- 路 A：uv pip freeze（主清单）------------------------------------
    uv_cmd = [uv, "pip", "freeze", "--python", str(venv_py)]
    rA = subprocess.run(uv_cmd, capture_output=True, text=True)
    invA = {"command": " ".join(uv_cmd), "rc": rA.returncode,
            "stderr_tail": rA.stderr[-300:]}
    if rA.returncode != 0 or not rA.stdout.strip():
        fatal(f"inventory-A (uv pip freeze) rc={rA.returncode} "
              f"stdout_empty={not rA.stdout.strip()} stderr={rA.stderr[-300:]}")
    versA, editableA, directA = parse_uv_freeze(rA.stdout)
    if len(versA) < MIN_PKGS:
        fatal(f"inventory-A package count {len(versA)} < floor {MIN_PKGS}")

    # ---- 路 B：importlib.metadata（独立交叉验证）------------------------
    rB = subprocess.run([str(venv_py), "-c", IMPLIB_SCRIPT],
                        capture_output=True, text=True)
    invB = {"command": f"{venv_py} -c <importlib.metadata enumeration>",
            "rc": rB.returncode, "stderr_tail": rB.stderr[-300:]}
    if rB.returncode != 0 or not rB.stdout.strip():
        fatal(f"inventory-B (importlib.metadata) rc={rB.returncode} "
              f"stdout_empty={not rB.stdout.strip()} stderr={rB.stderr[-300:]}")
    try:
        dists = json.loads(rB.stdout)
    except json.JSONDecodeError as e:
        fatal(f"inventory-B JSON decode failed: {e}")
    versB = {norm(d["name"]): d["version"] for d in dists}
    provB = [d for d in dists if d.get("direct_url_json") or d.get("local_file")]
    if len(versB) < MIN_PKGS:
        fatal(f"inventory-B package count {len(versB)} < floor {MIN_PKGS}")

    # ---- 双路规范化比对（非逐字一致；PEP 503 name→version）--------------
    onlyA = sorted(set(versA) - set(versB))
    onlyB = sorted(set(versB) - set(versA))
    vmis = sorted({"name": k, "uv": versA[k], "importlib": versB[k]}
                  for k in set(versA) & set(versB) if versA[k] != versB[k])
    cross = {"pep503_normalized": True, "uv_count": len(versA),
             "importlib_count": len(versB),
             "only_in_uv": onlyA, "only_in_importlib": onlyB,
             "version_mismatch": vmis,
             "verdict": "PASS" if not (onlyA or onlyB or vmis) else "FATAL"}
    if cross["verdict"] != "PASS":
        fatal(f"cross-inventory mismatch: onlyA={onlyA[:10]} onlyB={onlyB[:10]} "
              f"vmis={vmis[:10]}")

    # ---- 关键包：两路一致 + 与 Phase 02 基线一致 ------------------------
    key = {}
    key_drift = []
    bver = baseline.get("package_versions", {})
    for k in KEY_PKGS:
        nk = norm(k)
        va, vb = versA.get(nk), versB.get(nk)
        if va is None or vb is None or va != vb:
            key_drift.append({"pkg": k, "uv": va, "importlib": vb})
            continue
        ref = bver.get(k)
        key[k] = {"version": va, "phase02_baseline": ref,
                  "match_baseline": (ref == va)}
        if ref != va:
            key_drift.append({"pkg": k, "now": va, "phase02_baseline": ref})
    if key_drift:
        fatal(f"key package drift vs dual-source/baseline: {key_drift}")

    # ---- 全部校验通过 → atomic 写 freeze 与交叉验证原始件 ---------------
    atomic_write(FREEZE, rA.stdout)
    atomic_write(IMPLIB_RAW, json.dumps(dists, ensure_ascii=False, indent=1) + "\n")

    # ---- tree sha / patch 完整性 / provenance（继承 Phase 02 逻辑）------
    site = run([str(venv_py), "-c",
                "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
               what="sysconfig purelib").stdout.strip()
    vllm_root = Path(site) / "vllm"
    th, nfiles = tree_hash(vllm_root)

    patches = {p.name: sha256_file(p)
               for p in sorted((ENVDIR / "patch-units").glob("*.patch"))}

    ledger = json.loads((ENVDIR / "patched-files-ledger.json").read_text())
    drift, verified = [], []
    for ent in ledger.get("patches", []):
        f = ent.get("file")
        if not f:
            continue  # Layer C inert 单元无逐文件核对义务
        cur = vllm_root / f
        if not cur.exists():
            drift.append({"file": f, "issue": "MISSING_ON_DISK"})
            continue
        cur_sha = sha256_file(cur)
        want = ent.get("sha256_after", "").replace("-truncated", "")
        ok = (cur_sha == want) if want else None
        verified.append({"file": f, "match_with_phase01_ledger": ok})
        if ok is False:
            drift.append({"file": f, "issue": "SHA_DRIFT",
                          "phase01_after": want, "now": cur_sha})

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
    rP = subprocess.run([str(venv_py), "-c", prov_script], capture_output=True,
                        text=True,
                        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()),
                             "VLLM_DFLASH2_TORCH_TOPK": "1"})
    if rP.returncode != 0 or not rP.stdout.strip():
        fatal(f"symbol provenance probe rc={rP.returncode} stderr={rP.stderr[-300:]}")
    prov = json.loads(rP.stdout)

    # ---- 与 Phase 02 认证基线的继承比对 --------------------------------
    cmp_drift = list(drift)
    b_tree = baseline.get("vllm_tree", {}).get("sha256_post_patch")
    if th != b_tree:
        cmp_drift.append({"item": "vllm_tree_sha256",
                          "phase02": b_tree, "now": th})
    b_patch = baseline.get("patch_unit_files_sha256", {})
    for name, sha in patches.items():
        if b_patch.get(name) != sha:
            cmp_drift.append({"item": "patch_unit_sha", "file": name,
                              "phase02": b_patch.get(name), "now": sha})
    b_syms = baseline.get("symbol_provenance", {}).get("symbols", {})
    for k, ent in prov["symbols"].items():
        if "sha256" not in ent:
            cmp_drift.append({"item": "symbol_probe", "symbol": k,
                              "now": ent.get("error")})
            continue
        b_sha = b_syms.get(k, {}).get("sha256")
        if b_sha != ent["sha256"]:
            cmp_drift.append({"item": "symbol_sha", "symbol": k,
                              "phase02": b_sha, "now": ent["sha256"]})

    verdict = "ENV_DRIFT" if cmp_drift else "EVIDENCE_REPAIR"
    report = {
        "purpose": "Phase 03 P0A.1——runtime029 继承审计（fail-closed 重写）；"
                   "Phase 02 认证基线见 runtime029-phase02-baseline.json（不改写）",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "erratum_EP03_A1": {
            "issue": "Phase 02 版 p0a_runtime_freeze.py 用 `python -m pip freeze --all` "
                     "做包清单；uv venv 无 pip → rc!=0、stdout 空；未查 returncode "
                     "即写出 0 字节 freeze 文件并继续 CLEAN baseline（fail-open）",
            "old_freeze": old_freeze,
            "empty_sha256_const": hashlib.sha256(b"").hexdigest(),
            "fix": "双路清单（uv pip freeze + importlib.metadata）PEP 503 规范化比对，"
                   "rc/空输出/包数下限/关键包漂移全 FATAL；temp→校验→atomic rename",
            "classification": "evidence repair（若 comparison 零漂移）——非 ENV_DRIFT",
        },
        "uv": {"version": uv_ver},
        "inventory": {
            "A_uv_freeze": invA, "B_importlib": invB,
            "freeze_file": FREEZE.name,
            "freeze_sha256_now": sha256_file(FREEZE),
            "uv_freeze_pkgs": len(versA),
            "importlib_pkgs": len(versB),
            "cross_check": cross,
            "editable_or_direct_url_provenance": {
                "uv_side": {"editable": editableA, "direct_url": directA},
                "importlib_side_count": len(provB)},
            "key_packages": key,
        },
        "vllm_tree": {"root": str(vllm_root), "files_hashed": nfiles,
                      "sha256_post_patch": th},
        "patch_unit_files_sha256": patches,
        "patched_file_integrity": {"checked": verified,
                                   "verdict": "CLEAN" if not drift else "DRIFT"},
        "symbol_provenance": prov,
        "comparison_vs_phase02_baseline": {
            "drift": cmp_drift,
            "verdict": verdict,
        },
    }
    atomic_write(INHERIT, json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(f"[freeze] wrote {INHERIT}")
    print(f"[freeze] freeze {FREEZE.name}: {len(versA)} pkgs, "
          f"sha256={report['inventory']['freeze_sha256_now'][:16]}…")
    print(f"[freeze] vllm tree sha256 = {th[:16]}… ({nfiles} files)")
    print(f"[freeze] verdict = {verdict}")
    return 0 if verdict == "EVIDENCE_REPAIR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
