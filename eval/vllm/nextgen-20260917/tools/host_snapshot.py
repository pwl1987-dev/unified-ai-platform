#!/usr/bin/env python3
"""host-snapshot / env-lock 一次性生成（v2.1 第 2 条，MASTER §4.1 全集）。

生成不可变 repro/host-snapshot.json 与 repro/env-lock.json；
各实验 manifest 引用其 SHA256，不重复复制主机信息。
只读采集，不改任何系统状态。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nvml_bind  # noqa: E402

VENV = "/data/tools/vllm28-env"
OVERLAY = "/data/sandbox/vllm-cu130-qual-20260915/overlay-kvarn"


def run(cmd: list[str], timeout: int = 60) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else f"__ERR rc={r.returncode}"
    except Exception as e:  # noqa: BLE001
        return f"__ERR {str(e)[:120]}"


def sha256_file(p: str) -> str | None:
    if not os.path.exists(p):
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def collect_host() -> dict:
    gpus = nvml_bind.snapshot_gpus()
    return {
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": platform.node(),
        "kernel": platform.release(),
        "distro": run(["cat", "/etc/os-release"]).split("\n")[0],
        "cpu": {
            "model": run(["bash", "-c", "lscpu | grep 'Model name' | head -1"]),
            "cores": os.cpu_count(),
            "governor": run(["bash", "-c",
                             "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null"]) or "unknown",
            "microcode": run(["bash", "-c", "grep -m1 microcode /proc/cpuinfo"]),
        },
        "ram_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1),
        "motherboard": {
            "board": run(["bash", "-c", "cat /sys/class/dmi/id/board_name 2>/dev/null"]),
            "bios": run(["bash", "-c", "cat /sys/class/dmi/id/bios_version 2>/dev/null"]),
        },
        "gpus": [{k: c[k] for k in ("logical_index", "uuid", "pci_bdf", "name",
                                    "power_limit_w", "temp_c", "throttle_reasons")}
                 for c in gpus],
        "gpu_topology": run(["nvidia-smi", "topo", "-m"]),
        "gpu_detail": run(["nvidia-smi", "-q"]),
        "driver": run(["nvidia-smi", "--query-gpu=driver_version",
                       "--format=csv,noheader"]).split("\n")[0],
        "cuda_runtime": run(["nvidia-smi", "--query-gpu=cuda_version",
                             "--format=csv,noheader"]).split("\n")[0],
        "filesystems": run(["df", "-hT", "/data", "/tmp", "/"]),
        "kernel_cmdline": run(["bash", "-c", "cat /proc/cmdline"]),
        "iommu": run(["bash", "-c", "dmesg 2>/dev/null | grep -i -m2 'iommu\\|ACS'"]) or "unavailable",
        "aspm": run(["bash", "-c",
                     "lspci -vv 2>/dev/null | grep -m2 ASPM"]) or "unavailable",
        "numa": run(["bash", "-c", "lscpu | grep -i numa"]),
    }


def collect_env_lock() -> dict:
    vpy = os.path.join(VENV, "bin", "python")
    versions = run([vpy, "-c",
                    "import json;d={};import torch;d['torch']=torch.__version__;"
                    "import vllm;d['vllm']=vllm.__version__;"
                    "import flashinfer;d['flashinfer']=flashinfer.__version__;"
                    "import triton;d['triton']=triton.__version__;"
                    "d['python']=__import__('sys').version.split()[0];print(json.dumps(d))"],
                   timeout=120)
    try:
        vers = json.loads(versions)
    except Exception:  # noqa: BLE001
        vers = {"raw": versions}
    nccl = "unknown"
    try:
        import glob
        cands = glob.glob(os.path.join(VENV, "lib/python3.12/site-packages/nvidia/nccl/lib/libnccl.so*"))
        nccl = os.path.basename(cands[0]) if cands else "not-found"
    except Exception:  # noqa: BLE001
        pass
    return {
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "venv": VENV,
        "overlay_pythonpath": OVERLAY,
        "versions": vers,
        "nccl_lib": nccl,
        "pip_freeze_sha256": None,   # 由 --with-freeze 填充
        "compiler": run(["bash", "-c", "gcc --version 2>/dev/null | head -1"]),
        "glibc": platform.libc_ver()[1] if platform.libc_ver()[1] else "unknown",
        "apt_lock_sha256": None,
        "model_sha_manifest": "eval/vllm/cuda13/usable-concurrency-20260916/repro/manifests/model-sha256.txt",
    }


def main() -> int:
    host = collect_host()
    env = collect_env_lock()
    with_freeze = "--with-freeze" in sys.argv
    if with_freeze:
        freeze = run([os.path.join(VENV, "bin", "pip"), "freeze", "--all"], timeout=300)
        p = os.path.join(NEXTGEN, "repro", "pip-freeze.txt")
        with open(p, "w") as f:
            f.write(freeze + "\n")
        env["pip_freeze_sha256"] = sha256_file(p)
    hs_path = os.path.join(NEXTGEN, "repro", "host-snapshot.json")
    el_path = os.path.join(NEXTGEN, "repro", "env-lock.json")
    with open(hs_path, "w") as f:
        json.dump(host, f, indent=1, ensure_ascii=False)
    with open(el_path, "w") as f:
        json.dump(env, f, indent=1, ensure_ascii=False)
    print(json.dumps({
        "host_snapshot": hs_path, "host_sha256": sha256_file(hs_path),
        "env_lock": el_path, "env_lock_sha256": sha256_file(el_path),
        "gpus": len(host["gpus"]), "driver": host["driver"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
