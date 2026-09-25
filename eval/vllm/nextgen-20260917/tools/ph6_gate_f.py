#!/usr/bin/env python3
"""ph6_gate_f.py — Phase 06 Gate F 机器判定器（gates-phase06 gate_f，看结果前冻结）。

输入：
  F1: raw/staging/PH6-P1/{mix-blind,mix-role}/cell-summary.json（round-2 正式对）
      + role 轨 route log（placement audit）
  F2: raw/staging/PH6-P2/{isolation-role,isolation-blind}/cell-summary.json
  F3: raw/staging/PH6-P3/dual-{T2-B01..B03,T1-B04}/cell-summary.json（每 boot 每 rep 快照）
规则（frozen）：
  F1: short_p95_ttft B vs A 3% 带（lower better）；long_completion=1.0 硬门；
      batch_goodput/fairness 回退 ≤3% 带；placement=100% 才认 ROLE 有效执行
      → ROLE_REQUIRED / BLIND_SUFFICIENT / ROLE_REJECTED
  F2: 硬门 short_p95≤5.0s ∧ completions=1.0 ∧ jain≥0.90 ∧ failure_window=0
      + churn 全波完成 + evict（409 清晰错误/release≤15s/router 存活/inflight 归零）
      → ISOLATION_PASS / ISOLATION_FAIL（量化）
  F3: 漂移对照 |T1-B04 − T1_P3_ref| ≤3%；T2 3-boot 中位 ≥ T1 ref×1.03 ∧ 逐 boot 同向
      → CONFIRMED_DUAL_CHAMPION / DUAL_CO_CHAMPION / OVERTURNED
输出：raw/staging/PH6-P4/gate-f-verdict.json
自测：--selftest 合成 cell-summaries → 断言三问全部路径（含边界带内/带外/漂移升级）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics

EPS = 0.03
NG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ST = os.path.join(NG, "raw", "staging")
F2_BOUND_S = 5.0
F2_JAIN_MIN = 0.90
F2_RELEASE_MAX_S = 15.0
T1_P3_REF = 15.249            # PH5-P3 ph5-matrix.json dual_p32k_sess_decode[T1]（对照锚）


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def validate_schema(cs: dict) -> tuple[bool, str]:
    req_top = ["scenario", "policy", "wall_s", "per_role", "per_session",
               "fairness_jain_goodput", "failure_window_s"]
    for k in req_top:
        if k not in cs:
            return False, f"missing top field {k}"
    for role in ("short", "long", "batch"):
        if role not in cs.get("per_role", {}):
            return False, f"missing per_role.{role}"
        r = cs["per_role"][role]
        for k in ("requests", "ok", "completion_rate", "ttft_p95"):
            if k not in r:
                return False, f"missing per_role.{role}.{k}"
    return True, "ok"


def placement_audit(route_log: str) -> dict:
    """role 轨 route log：short/batch→TP1*、long→TP2；accuracy=正确路由占比。"""
    total, good = 0, 0
    per_role_backend: dict[str, dict] = {}
    for line in open(route_log):
        try:
            r = json.loads(line)
        except Exception:
            continue
        role, backend = r.get("role"), r.get("backend")
        if not role or not backend:
            continue
        total += 1
        want_tp1 = role in ("short", "batch")
        ok = backend.startswith(("t3p1", "p1")) if want_tp1 else backend.startswith(("t3tp2", "tp2"))
        good += ok
        per_role_backend.setdefault(role, {}).setdefault(backend, 0)
        per_role_backend[role][backend] += 1
    acc = round(good / total, 4) if total else None
    return {"requests": total, "accurate": good, "accuracy": acc,
            "per_role_backend": per_role_backend}


# ---------------------------------------------------------------- F1
def judge_f1(mix_a: dict, mix_b: dict, placement: dict) -> dict:
    a, b = mix_a["per_role"], mix_b["per_role"]
    sa, sb = a["short"]["ttft_p95"], b["short"]["ttft_p95"]
    axes = {}
    if sa is not None and sb is not None:
        axes["short_p95_ttft_rel_gain"] = round((sa - sb) / sa, 4)   # 正=B 更低（更好）
        axes["short_p95_band_out"] = abs((sa - sb) / sa) > EPS
    else:
        axes["short_p95_ttft_rel_gain"] = None
        axes["short_p95_band_out"] = False
    bg_a, bg_b = a["batch"], b["batch"]
    # batch goodput 代理：per-role 总输出 token / 场景墙钟（两臂同形制同墙钟语义，可比）
    def bg_goodput(x, wall):
        return round(x["sum_output_tokens"] / wall, 3) if wall and x["sum_output_tokens"] else None
    ga, gb = bg_goodput(bg_a, mix_a["wall_s"]), bg_goodput(bg_b, mix_b["wall_s"])
    if ga and gb:
        axes["batch_goodput_rel"] = round((gb - ga) / ga, 4)
    else:
        axes["batch_goodput_rel"] = None
    ja, jb = mix_a["fairness_jain_goodput"], mix_b["fairness_jain_goodput"]
    axes["fairness_a"], axes["fairness_b"] = ja, jb
    hard_long = (a["long"]["completion_rate"] == 1.0 and b["long"]["completion_rate"] == 1.0)
    axes["long_completion_both_1"] = hard_long
    axes["placement_accuracy"] = placement.get("accuracy")
    # 判定（frozen）
    if not hard_long:
        verdict = "ROLE_REJECTED"          # 任一臂长完成率<1 → 场景本身失败，禁判路由优劣
        reason = "long completion rate != 1.0 in at least one arm"
    elif axes["short_p95_band_out"] and axes["short_p95_ttft_rel_gain"] > 0:
        regress = []
        if axes["batch_goodput_rel"] is not None and axes["batch_goodput_rel"] < -EPS:
            regress.append("batch_goodput")
        if jb is not None and ja is not None and (jb - ja) / ja < -EPS:
            regress.append("fairness")
        if b["short"]["completion_rate"] is not None and b["short"]["completion_rate"] < 1.0:
            regress.append("short_completion")
        if regress:
            verdict, reason = "ROLE_REJECTED", f"regressions: {regress}"
        elif placement.get("accuracy") != 1.0:
            verdict, reason = "ROLE_REJECTED", f"placement accuracy {placement.get('accuracy')} != 1.0"
        else:
            verdict, reason = "ROLE_REQUIRED", "short P95 out-of-band better, no regression, placement 100%"
    elif axes["short_p95_band_out"] and axes["short_p95_ttft_rel_gain"] < 0:
        verdict, reason = "ROLE_REJECTED", "short P95 worse out-of-band under role routing"
    else:
        verdict, reason = "BLIND_SUFFICIENT", "all axes within 3% band (EQUIVALENT) — simpler router wins"
    return {"question": "F1_role_routing", "verdict": verdict, "reason": reason,
            "axes": axes,
            "short_p95_ttft": {"A_blind": sa, "B_role": sb},
            "batch_goodput_proxy": {"A": ga, "B": gb},
            "values": {"A": {"short_p95": sa, "long_completion": a["long"]["completion_rate"],
                             "fairness": ja},
                       "B": {"short_p95": sb, "long_completion": b["long"]["completion_rate"],
                             "fairness": jb}},
            "placement": placement}


# ---------------------------------------------------------------- F2
def judge_f2(iso: dict, iso_blind: dict | None) -> dict:
    roles = iso["per_role"]
    short = roles["short"]
    lng = roles["long"]
    gates = {
        "short_p95_ttft_le_bound": short["ttft_p95"] is not None and short["ttft_p95"] <= F2_BOUND_S,
        "short_completion_eq_1": short["completion_rate"] == 1.0,
        "long_completion_eq_1_excl_evicted": (
            lng["requests"] and
            (lng["ok"] + lng["errors"].get("EVICTED", 0)) / lng["requests"] == 1.0),
        "jain_short_ge_min": (iso["fairness_jain_goodput"] or 0) >= F2_JAIN_MIN,
        "failure_window_zero": iso["failure_window_s"] == 0,
        "churn_all_complete": all(v.get("requests") == v.get("ok")
                                  and (v.get("ok") or 0) > 0
                                  for k, v in iso["per_session"].items()
                                  if k.startswith("churn-"))
                                  and any(k.startswith("churn-")
                                          for k in iso["per_session"]),
        "session_map_no_leak": all(v == 0 for v in (iso.get("backends_inflight_after") or {}).values()),
    }
    ev = iso.get("evict") or {}
    gates["evict_client_clear_error"] = bool(ev.get("evicted_session"))
    gates["evict_release_le_bound"] = (ev.get("release_latency_s") is not None
                                       and ev["release_latency_s"] <= F2_RELEASE_MAX_S)
    gates["evict_probe_ok"] = bool(ev.get("probe_ok"))
    verdict = "ISOLATION_PASS" if all(gates.values()) else "ISOLATION_FAIL"
    out = {"question": "F2_tenant_isolation", "verdict": verdict, "gates": gates,
           "values": {"short_p95_ttft_s": short["ttft_p95"],
                      "short_completion": short["completion_rate"],
                      "long_completion_excl_evicted": gates["long_completion_eq_1_excl_evicted"],
                      "jain": iso["fairness_jain_goodput"],
                      "failure_window_s": iso["failure_window_s"],
                      "evict": ev,
                      "errors_long": lng.get("errors"),
                      "bound_s": F2_BOUND_S},
           "starvation_reference": {"PH5_mixed_T2_short_p95_s": 50.4439,
                                    "PH5_mixed_T3_short_p95_s": 0.2699}}
    if iso_blind:
        sb = iso_blind["per_role"]["short"]
        out["blind_comparison"] = {"short_p95_ttft_s": sb["ttft_p95"],
                                   "short_completion": sb["completion_rate"],
                                   "failure_window_s": iso_blind["failure_window_s"],
                                   "jain": iso_blind["fairness_jain_goodput"]}
    return out


# ---------------------------------------------------------------- F3
def dual_sess_decode(cs: dict) -> float | None:
    d = cs.get("sessions") or {}
    vals = [(v.get("sum_output_tokens") or 0) / (v.get("batch_wall_s") or 1)
            for v in d.values()]
    return round(statistics.median(vals), 3) if vals else None


def judge_f3(t2_boot_dirs: dict[str, list[str]], t1_ctrl_dirs: list[str]) -> dict:
    """t2_boot_dirs: {B01: [cell-summary 路径 ×reps]}；t1_ctrl_dirs: [paths]。"""
    t2_boot_med = {}
    for boot, paths in t2_boot_dirs.items():
        vals = [dual_sess_decode(_load(p)) for p in paths]
        vals = [v for v in vals if v is not None]
        t2_boot_med[boot] = round(statistics.median(vals), 3) if vals else None
    t1_vals = [dual_sess_decode(_load(p)) for p in t1_ctrl_dirs]
    t1_vals = [v for v in t1_vals if v is not None]
    t1_ctrl = round(statistics.median(t1_vals), 3) if t1_vals else None
    drift = round((t1_ctrl - T1_P3_REF) / T1_P3_REF, 4) if t1_ctrl else None
    out = {"question": "F3_t2_3boot", "t2_boot_medians": t2_boot_med,
           "t1_control": {"boot_med": t1_ctrl, "p3_ref": T1_P3_REF, "drift_rel": drift},
           "drift_ok": drift is not None and abs(drift) <= EPS,
           "escalate_full_matrix": drift is not None and abs(drift) > EPS}
    if not out["drift_ok"]:
        out["verdict"] = "DRIFT_ESCALATION_REQUIRED"
        out["reason"] = "T1 control boot deviates >3% from P3 reference — rerun same-day full matrix"
        return out
    t2_vals = [v for v in t2_boot_med.values() if v is not None]
    if not t2_vals:
        out["verdict"] = "INVALID"
        out["reason"] = "no T2 dual values"
        return out
    t2_med = round(statistics.median(t2_vals), 3)
    out["t2_3boot_median"] = t2_med
    out["rel_vs_t1"] = round((t2_med - T1_P3_REF) / T1_P3_REF, 4)
    direction_consistent = all(v > T1_P3_REF for v in t2_vals)
    out["per_boot_direction_positive"] = direction_consistent
    if out["rel_vs_t1"] >= EPS and direction_consistent:
        out["verdict"] = "CONFIRMED_DUAL_CHAMPION"
        out["reason"] = f"T2 3-boot median {t2_med} >= T1 ref {T1_P3_REF} +3% and all boots positive"
    elif out["rel_vs_t1"] < -EPS:
        out["verdict"] = "OVERTURNED"
        out["reason"] = f"T2 3-boot median {t2_med} below T1 ref {T1_P3_REF} beyond band"
    else:
        out["verdict"] = "DUAL_CO_CHAMPION"
        out["reason"] = "within 3% band — screen-level +12.1% not reproduced cross-boot"
    return out


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--validate-schema", action="store_true",
                    help="校验全部 PH6 cell-summary；全部合法才允许 verdict")
    ap.add_argument("--emit", action="store_true", help="从 staging 正式产出 gate-f-verdict.json")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.validate_schema:
        bad = []
        for p in glob.glob(os.path.join(ST, "PH6-*", "*", "cell-summary.json")):
            ok, why = validate_schema(_load(p))
            if not ok:
                bad.append({"path": p, "why": why})
        print(json.dumps({"schema_check": "PASS" if not bad else "FAIL", "bad": bad},
                         ensure_ascii=False, indent=1))
        return 0 if not bad else 1
    if args.emit:
        # 实际布局：mix/isolation 场景统一落 PH6-P1（ph6_p1_run 单目录）；P3 快照在 PH6-P3
        f1a = _load(os.path.join(ST, "PH6-P1", "mix-blind-r2", "cell-summary.json"))
        f1b = _load(os.path.join(ST, "PH6-P1", "mix-role-r2", "cell-summary.json"))
        placement = placement_audit(os.path.join(ST, "PH6-P1", "routes-role.jsonl"))
        f2 = judge_f2(_load(os.path.join(ST, "PH6-P1", "isolation-role-r2", "cell-summary.json")),
                      _load(os.path.join(ST, "PH6-P1", "isolation-blind-r2", "cell-summary.json")))
        # F3 取数：每 boot 只取 R1（冷前缀=PH5 每 boot 单次执行同形制；R2/R3 为
        # 同 prompt 前缀缓存热化观测，单独报告不入 verdict——形制勘误见 PH6-P3 说明）
        t2_boots = {b: [os.path.join(ST, "PH6-P3", f"dual-T2-{b}-R1", "cell-summary.json")]
                    for b in ("B01", "B02", "B03")}
        t1_ctrl = [os.path.join(ST, "PH6-P3", "dual-T1-B04-R1", "cell-summary.json")]
        f3 = judge_f3(t2_boots, t1_ctrl)
        # 辅助：warm reps（前缀缓存稳态）——供报告，不入判定
        for b in ("B01", "B02", "B03"):
            warm = sorted(glob.glob(os.path.join(ST, "PH6-P3", f"dual-T2-{b}-R[23]",
                                                 "cell-summary.json")))
            vals = [dual_sess_decode(_load(p)) for p in warm]
            f3.setdefault("aux_prefix_warm_reps", {})[b] = vals
        verdict = {
            "gate_f": {
                "F1_role_routing": judge_f1(f1a, f1b, placement),
                "F2_tenant_isolation": f2,
                "F3_t2_3boot": f3,
            },
            "epsilon_band": EPS,
            "inputs": ["raw/staging/PH6-P1", "raw/staging/PH6-P2", "raw/staging/PH6-P3"],
        }
        os.makedirs(os.path.join(ST, "PH6-P4"), exist_ok=True)
        out = os.path.join(ST, "PH6-P4", "gate-f-verdict.json")
        json.dump(verdict, open(out, "w"), indent=1, ensure_ascii=False)
        print(json.dumps(verdict["gate_f"], ensure_ascii=False, indent=1)[:2000])
        print("WROTE", out)
        return 0
    ap.error("需要 --selftest / --validate-schema / --emit 之一")
    return 2


def selftest() -> int:
    def cs(short_p95, long_comp=1.0, batch_ok=8, jain=0.99, fw=0.0, short_ok=12):
        return {"scenario": "mix", "policy": "x", "wall_s": 60, "failure_window_s": fw,
                "fairness_jain_goodput": jain,
                "per_role": {
                    "short": {"requests": 12, "ok": short_ok,
                              "completion_rate": short_ok / 12, "ttft_p95": short_p95},
                    "long": {"requests": 3, "ok": int(3 * long_comp),
                             "completion_rate": long_comp, "ttft_p95": 8.0},
                    "batch": {"requests": 8, "ok": batch_ok, "completion_rate": batch_ok / 8,
                              "ttft_p95": 2.0, "sum_output_tokens": batch_ok * 256,
                              "wall_med": batch_ok * 1.0}},
                "per_session": {}}
    pl = {"accuracy": 1.0}
    # 1) B 出带胜 → ROLE_REQUIRED
    v = judge_f1(cs(1.0), cs(0.5), pl)
    assert v["verdict"] == "ROLE_REQUIRED", v
    # 2) 带内 → BLIND_SUFFICIENT
    v = judge_f1(cs(1.0), cs(0.99), pl)
    assert v["verdict"] == "BLIND_SUFFICIENT", v
    # 3) B 更差出带 → ROLE_REJECTED
    v = judge_f1(cs(1.0), cs(1.5), pl)
    assert v["verdict"] == "ROLE_REJECTED", v
    # 4) B 胜但 batch 回退 >3% → ROLE_REJECTED
    v = judge_f1(cs(1.0), cs(0.5, batch_ok=4), pl)
    assert v["verdict"] == "ROLE_REJECTED", v
    # 5) B 胜但 placement<100% → ROLE_REJECTED
    v = judge_f1(cs(1.0), cs(0.5), {"accuracy": 0.95})
    assert v["verdict"] == "ROLE_REJECTED", v
    # F2
    iso = {"per_role": {"short": {"requests": 24, "ok": 24, "completion_rate": 1.0, "ttft_p95": 0.4},
                        "long": {"requests": 28, "ok": 24, "completion_rate": 0.857,
                                 "errors": {"EVICTED": 4}}},
           "per_session": {"churn-1": {"requests": 3, "ok": 3}, "res-1": {"requests": 6, "ok": 6}},
           "fairness_jain_goodput": 0.95, "failure_window_s": 0,
           "backends_inflight_after": {"t3tp2": 0},
           "evict": {"evicted_session": "hog-1", "release_latency_s": 3.2, "probe_ok": True}}
    v = judge_f2(iso, None)
    assert v["verdict"] == "ISOLATION_PASS", v
    iso2 = json.loads(json.dumps(iso))
    iso2["per_role"]["short"]["ttft_p95"] = 6.0
    v = judge_f2(iso2, None)
    assert v["verdict"] == "ISOLATION_FAIL", v
    iso3 = json.loads(json.dumps(iso))
    iso3["evict"]["release_latency_s"] = 20.0
    v = judge_f2(iso3, None)
    assert v["verdict"] == "ISOLATION_FAIL", v
    # F3
    def dcs(val):
        return {"sessions": {"da": {"sum_output_tokens": 256, "batch_wall_s": 256 / val},
                             "db": {"sum_output_tokens": 256, "batch_wall_s": 256 / val}}}
    t2 = {b: ["x"] for b in ("B01", "B02", "B03")}
    t1 = ["y"]
    # 6) T2 三 boot 全胜出带 → CONFIRMED（drift 对照 15.1 ≈ ref）
    import tempfile
    td = tempfile.mkdtemp()
    paths = {}
    for boot, val in (("B01", 17.5), ("B02", 17.0), ("B03", 17.2)):
        p = os.path.join(td, f"t2-{boot}.json")
        json.dump(dcs(val), open(p, "w"))
        paths[boot] = [p]
    p_t1 = os.path.join(td, "t1.json")
    json.dump(dcs(15.1), open(p_t1, "w"))
    v = judge_f3(paths, [p_t1])
    assert v["verdict"] == "CONFIRMED_DUAL_CHAMPION", v
    # 7) T2 带内 → CO_CHAMPION
    for boot, val in (("B01", 15.5), ("B02", 15.3), ("B03", 15.4)):
        p = os.path.join(td, f"t2b-{boot}.json")
        json.dump(dcs(val), open(p, "w"))
        paths[boot] = [p]
    v = judge_f3(paths, [p_t1])
    assert v["verdict"] == "DUAL_CO_CHAMPION", v
    # 8) 漂移超带 → 升级
    p_t1d = os.path.join(td, "t1-drift.json")
    json.dump(dcs(13.0), open(p_t1d, "w"))
    v = judge_f3(paths, [p_t1d])
    assert v["verdict"] == "DRIFT_ESCALATION_REQUIRED", v
    # 9) schema 校验负例
    ok, why = validate_schema({"scenario": "mix"})
    assert not ok and "missing" in why, (ok, why)
    print(json.dumps({"selftest": "SELFTEST_PASS",
                      "f1_paths": "REQUIRED/SUFFICIENT/REJECTED×3",
                      "f2_paths": "PASS/FAIL(p95)/FAIL(release)",
                      "f3_paths": "CONFIRMED/CO/DRIFT"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
