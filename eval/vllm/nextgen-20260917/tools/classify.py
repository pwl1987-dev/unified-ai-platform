#!/usr/bin/env python3
"""证据分类归档器：schema 校验 → 六态 status → staging 原子归档（v2.1 第 1/4/7 条）。

状态机（双字段）：
  evidence_class = staging | valid | invalid | unsupported   （目录三分类）
  status = VALID_PASS | VALID_FAIL | INVALID | UNSUPPORTED | ABORTED | REJECTED

判定规则（优先级从高到低）：
  1. schema 校验失败                  -> INVALID / SCHEMA_FAIL
  2. manifest 显式 server_crash       -> INVALID / SERVER_CRASH
  3. manifest 显式 harness_error      -> INVALID / HARNESS_ERROR
  4. manifest 显式 env_drift          -> INVALID / ENV_DRIFT
  5. manifest 显式 interrupted        -> ABORTED / INTERRUPTED
  6. run_validity 未过（采样器/计数错）-> INVALID / HARNESS_ERROR
  7. OOM（真实服务端拒绝且测量链完好） -> VALID_FAIL / OOM
  8. 质量门失败                        -> VALID_FAIL / QUALITY_FAIL
  9. 性能门失败                        -> VALID_FAIL / PERF_GATE_FAIL
  10. 全部通过                         -> VALID_PASS / null

用法:
  classify.py scan-staging                     # 恢复扫描（崩溃恢复，v2.1 第 14 条）
  classify.py <experiment-id> [--reason-key perf_gate_fail|quality_fail|oom|...]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
RAW = os.path.join(NEXTGEN, "raw")
SCHEMA_DIR = os.path.join(NEXTGEN, "repro", "schema")

REASON_TO_STATUS = {
    "PERF_GATE_FAIL": ("VALID_FAIL", "valid"),
    "QUALITY_FAIL": ("VALID_FAIL", "valid"),
    "OOM": ("VALID_FAIL", "valid"),          # 真实 OOM = 有效负结果
    "SERVER_CRASH": ("INVALID", "invalid"),
    "HARNESS_ERROR": ("INVALID", "invalid"),
    "ENV_DRIFT": ("INVALID", "invalid"),
    "SCHEMA_FAIL": ("INVALID", "invalid"),
    "INTERRUPTED": ("ABORTED", "invalid"),   # ABORTED 状态存 invalid 目录（非有效证据）
    "UNSUPPORTED": ("UNSUPPORTED", "unsupported"),
}


def load_schema(name: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, name)) as f:
        return json.load(f)


def validate_jsonschema(instance: dict, schema: dict, path: str = "$") -> list[str]:
    """极简 draft-07 子集校验（type/required/enum/pattern/properties/items/minimum）。
    足够本战役 schema；不引第三方依赖。"""
    errs: list[str] = []
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        def _type_ok(v, tn):
            return {"object": dict, "array": list, "string": str, "integer": int,
                    "number": (int, float), "boolean": bool,
                    "null": type(None)}.get(tn, object) and (
                (tn == "integer" and isinstance(v, int) and not isinstance(v, bool))
                or (tn == "number" and isinstance(v, (int, float)) and not isinstance(v, bool))
                or (tn == "boolean" and isinstance(v, bool))
                or (tn == "string" and isinstance(v, str))
                or (tn == "object" and isinstance(v, dict))
                or (tn == "array" and isinstance(v, list))
                or (tn == "null" and v is None))
        if not any(_type_ok(instance, tn) for tn in types):
            return [f"{path}: type mismatch, want {types}, got {type(instance).__name__}"]
    for req in schema.get("required", []):
        if req not in instance:
            errs.append(f"{path}: missing required '{req}'")
    if "enum" in schema and instance not in schema["enum"]:
        errs.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            errs.append(f"{path}: '{instance[:40]}' fails pattern {schema['pattern']}")
    if "minimum" in schema and isinstance(instance, (int, float)) and instance < schema["minimum"]:
        errs.append(f"{path}: {instance} < minimum {schema['minimum']}")
    if isinstance(instance, dict):
        for k, sub in (schema.get("properties") or {}).items():
            if k in instance:
                errs += validate_jsonschema(instance[k], sub, f"{path}.{k}")
    if isinstance(instance, list) and schema.get("items"):
        for i, item in enumerate(instance):
            errs += validate_jsonschema(item, schema["items"], f"{path}[{i}]")
    return errs


def validate_experiment(exp_dir: str) -> list[str]:
    errs = []
    mfile = os.path.join(exp_dir, "manifest.json")
    if not os.path.exists(mfile):
        return [f"missing manifest.json"]
    manifest = json.load(open(mfile))
    errs += [f"manifest: {e}" for e in
             validate_jsonschema(manifest, load_schema("manifest.schema.json"))]
    mfile2 = os.path.join(exp_dir, "metrics.json")
    if os.path.exists(mfile2):
        metrics = json.load(open(mfile2))
        errs += [f"metrics: {e}" for e in
                 validate_jsonschema(metrics, load_schema("metrics.schema.json"))]
    else:
        errs.append("missing metrics.json")
    rfile = os.path.join(exp_dir, "raw-events.jsonl")
    if os.path.exists(rfile):
        raw_schema = load_schema("raw-events.schema.json")
        for i, ln in enumerate(open(rfile)):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except Exception as e:  # noqa: BLE001
                errs.append(f"raw-events line {i}: bad json {e}")
                continue
            errs += [f"raw-events[{i}]: {e}" for e in validate_jsonschema(rec, raw_schema)]
    else:
        errs.append("missing raw-events.jsonl")
    return errs


def run_validity_check(exp_dir: str) -> list[str]:
    """gates-phase00.yaml run_validity 的本地实现。"""
    errs = []
    mf = os.path.join(exp_dir, "metrics.json")
    if not os.path.exists(mf):
        return ["no metrics.json"]
    m = json.load(open(mf))
    for key in ("metrics_endpoint", "nvml"):
        st = m.get("sampler_stats", {}).get(key, {})
        if st.get("sampler_exit_code") != 0:
            errs.append(f"sampler {key} exit_code={st.get('sampler_exit_code')}")
        msr = st.get("missing_sample_ratio")
        if msr is not None and msr > 0.05:
            errs.append(f"sampler {key} missing_ratio={msr}")
    if m.get("count_mismatch_samples", 0) > 0:
        errs.append(f"count_mismatch_samples={m['count_mismatch_samples']}")
    if m.get("http_errors", 0) > 0:
        errs.append(f"http_errors={m['http_errors']}")
    return errs


def classify(exp_id: str, reason_key: str | None = None,
             oom_server_side: bool = False) -> int:
    staging = os.path.join(RAW, "staging", exp_id)
    if not os.path.isdir(staging):
        print(f"ERROR: no staging dir {staging}", file=sys.stderr)
        return 2
    manifest_path = os.path.join(staging, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}

    if reason_key == "unsupported":
        status, cls, reason = *REASON_TO_STATUS["UNSUPPORTED"], "UNSUPPORTED"
    else:
        errs = validate_experiment(staging)
        if errs:
            status, cls, reason = "INVALID", "invalid", "SCHEMA_FAIL"
            manifest["validation_errors"] = errs[:20]
        else:
            v = run_validity_check(staging)
            explicit = (manifest.get("classification_reason") or "").upper() or None
            if explicit in ("SERVER_CRASH", "HARNESS_ERROR", "ENV_DRIFT", "INTERRUPTED"):
                status, cls = REASON_TO_STATUS[explicit]
                reason = explicit
            elif v:
                status, cls, reason = "INVALID", "invalid", "HARNESS_ERROR"
                manifest["validity_errors"] = v[:20]
            elif reason_key == "oom" or oom_server_side:
                status, cls, reason = *REASON_TO_STATUS["OOM"], "OOM"
            elif reason_key == "quality_fail":
                status, cls, reason = *REASON_TO_STATUS["QUALITY_FAIL"], "QUALITY_FAIL"
            elif reason_key == "perf_gate_fail":
                status, cls, reason = *REASON_TO_STATUS["PERF_GATE_FAIL"], "PERF_GATE_FAIL"
            else:
                status, cls, reason = "VALID_PASS", "valid", None

    manifest["status"] = status
    manifest["evidence_class"] = cls
    manifest["classification_reason"] = reason if status != "VALID_PASS" else None
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)

    dest = os.path.join(RAW, cls, exp_id)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.rename(staging, dest)   # 同文件系统原子移动
    print(json.dumps({"experiment_id": exp_id, "status": status,
                      "evidence_class": cls, "classification_reason":
                      manifest.get("classification_reason"), "archived_to": dest}))
    return 0


def scan_staging() -> int:
    """崩溃恢复扫描（v2.1 第 14 条）：完整证据补分类；不完整标 ABORTED/INTERRUPTED。"""
    staging_root = os.path.join(RAW, "staging")
    results = []
    for exp_id in sorted(os.listdir(staging_root)):
        p = os.path.join(staging_root, exp_id)
        if not os.path.isdir(p):
            continue
        complete = all(os.path.exists(os.path.join(p, f)) for f in
                       ("manifest.json", "metrics.json", "raw-events.jsonl"))
        if complete:
            r = classify(exp_id)
            results.append({"exp": exp_id, "recovered": r == 0})
        else:
            mf = os.path.join(p, "manifest.json")
            manifest = json.load(open(mf)) if os.path.exists(mf) else {}
            manifest.update({"status": "ABORTED", "evidence_class": "invalid",
                             "classification_reason": "INTERRUPTED",
                             "abort_note": "stale staging: incomplete evidence set"})
            with open(mf, "w") as f:
                json.dump(manifest, f, indent=1, ensure_ascii=False)
            dest = os.path.join(RAW, "invalid", exp_id)
            if not os.path.exists(dest):
                os.rename(p, dest)
            results.append({"exp": exp_id, "aborted": True})
    print(json.dumps(results, ensure_ascii=False))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    if sys.argv[1] == "scan-staging":
        return scan_staging()
    exp_id = sys.argv[1]
    reason = None
    for i, a in enumerate(sys.argv):
        if a == "--reason-key" and i + 1 < len(sys.argv):
            reason = sys.argv[i + 1].lower()
    return classify(exp_id, reason)


if __name__ == "__main__":
    sys.exit(main())
