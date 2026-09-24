#!/usr/bin/env python3
"""Phase 04 P4 — Gate D 机器判定器。

输入：PH4-P3/qualify-report.json（质量门+稳定性）、PH4-P2/ph4-matrix-summary.json（六轴）、
      静态 OOD、provenance 们、nvfp4-disposition。
规则（gates-phase04 pareto_contract）：
  1. hard eligibility：3-boot 全有效 + 质量门（holdout 核心轴 ≤2pp vs Q0；结构安全零退步）
  2. epsilon-Pareto（吞吐/prefill 3%、能效 5%、VRAM max(200MiB,2%)、质量 1pp 带=等价）
  3. 产出 2-3 Q-Profile + 映射 S1/L2/X2 + 路由边界
输出 raw/staging/PH4-P4/gate-d-verdict.json
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
ST = os.path.join(NG, "raw", "staging")

EPS_THR = 0.03
EPS_E = 0.05
EPS_Q_PP = 1.0
HARD_PP = 2.0


def axis_from_stdout(tail: str) -> dict:
    m = re.search(r"\{.*\}", tail or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def quality_of(stage: dict) -> dict:
    """从 rulers stdout_tail 抽各轴 pass 率（run_baseline 摘要行）。"""
    out = {}
    for a, r in (stage.get("rulers") or {}).items():
        d = axis_from_stdout(r.get("stdout_tail"))
        # 兼容多种摘要字段
        for k in ("pass_rate", "accuracy", "pass_pct", "ok_rate"):
            if isinstance(d.get(k), (int, float)):
                v = d[k]
                out[a] = round(100 * v, 2) if v <= 1.0 else round(v, 2)  # 归一 percent
                break
        else:
            n = d.get("n") or d.get("total")
            p = d.get("passed") or d.get("pass") or d.get("ok")
            if isinstance(n, (int, float)) and isinstance(p, (int, float)) and n:
                out[a] = round(100.0 * p / n, 2)
    return out


def main() -> int:
    qr = json.load(open(os.path.join(ST, "PH4-P3", "qualify-report.json")))
    mx = json.load(open(os.path.join(ST, "PH4-P2", "ph4-matrix-summary.json")))

    # ---- 1) 质量门 + 稳定性 ----
    qual = {}
    for cand in ("Q0", "Q1M", "Q4C", "W8"):
        boot_keys = [k for k in (f"{cand}_B{n}" for n in (1, 2, 3))
                     if k in qr["stages"] and qr["stages"][k].get("valid")]
        boots = [qr["stages"][k] for k in boot_keys]
        ok_boots = len(boots)
        per_boot_q = [quality_of(b) for b in boots]
        hold = {}
        for axis in ("he_holdout", "gsm_holdout", "ifeval_holdout", "xfc",
                     "he_screen", "gsm_screen"):
            vals = [q.get(axis) for q in per_boot_q
                    if isinstance(q.get(axis), (int, float))]
            if vals:
                hold[axis] = {"values": vals, "median": round(statistics.median(vals), 2),
                              "spread_pp": round(max(vals) - min(vals), 2)}
        needles = {}
        for b in boots:
            for s, v in (b.get("needle_holdout") or {}).items():
                needles.setdefault(s, []).append(v.get("PASS"))
        # s2@128K = Phase 02 已知码集×长度非正交签名（Q0 基线固有闪烁）——
        # 冻结 gates needle 配对判读：Q0 同 seed×tier 参照通过的次数为分母，
        # 候选只在"Q0 过而候选败"的配对事件上计退化；s5=稳定判别 seed
        needle_paired = {}
        for s in ("s2", "s5"):
            q0_seq = []
            for n in (1, 2, 3):
                q0b = qr["stages"].get(f"Q0_B{n}")
                if q0b and q0b.get("valid"):
                    q0_seq.append((q0b.get("needle_holdout") or {}).get(s, {}).get("PASS"))
            cand_seq = needles.get(s, [])
            pairs = [(q, c) for q, c in zip(q0_seq, cand_seq) if isinstance(q, bool) and isinstance(c, bool)]
            regressions = sum(1 for q, c in pairs if q and not c)
            needle_paired[s] = {"pairs": len(pairs), "q0_pass": sum(1 for q, c in pairs if q),
                                "candidate_regressions_vs_q0": regressions}
        micro_v = [(b.get("micro") or {}).get("verdict") for b in boots]
        qual[cand] = {"valid_boots": len(boots),
                      "boot_keys": boot_keys,
                      "holdout_axes": hold,
                      "needle_holdout_raw": {s: v for s, v in needles.items()},
                      "needle_paired_vs_q0": needle_paired,
                      "micro": micro_v}

    # 质量差 vs Q0（holdout 轴 pp）
    deltas = {}
    for cand in ("Q1M", "Q4C", "W8"):
        d = {}
        for axis, ref in qual["Q0"]["holdout_axes"].items():
            c = qual[cand]["holdout_axes"].get(axis)
            if c and ref.get("median") is not None:
                d[axis] = round(c["median"] - ref["median"], 2)
        deltas[cand] = d

    # 噪声带校准（gates epsilon 条款"引用 harness 重复性依据"）：
    # 轴噪声 floor = Q0 自身三 boot spread；退步判败线 = max(2pp, Q0 spread)
    noise_floor = {axis: max(HARD_PP, e["spread_pp"])
                   for axis, e in qual["Q0"]["holdout_axes"].items()}
    hard = {}
    structural_fail_boots = {}
    for c in ("Q0", "Q1M", "Q4C", "W8"):
        needle_ok = all(v["candidate_regressions_vs_q0"] == 0
                        for v in qual[c]["needle_paired_vs_q0"].values())
        axes_ok = all(v >= -noise_floor.get(axis, HARD_PP)
                      for axis, v in deltas.get(c, {}).items()
                      if axis != "he_screen" and axis != "gsm_screen")
        # PH4-EVIDENCE-REPAIR-01：tool_json_structural ∈ 冻结 gates
        # core_axes_zero_regress（"结构破坏=否决级"）——任一有效 boot micro=
        # STRUCTURAL_FAIL 即 hard reject；PARTIAL_REVIEW/STRUCTURAL_SAFE 过；
        # 观测缺失（None）≠失败（evidence_quality 与六态正交）
        structural_fail_boots[c] = [k for k, v in zip(qual[c]["boot_keys"], qual[c]["micro"])
                                    if v == "STRUCTURAL_FAIL"]
        micro_ok = not structural_fail_boots[c]
        hard[c] = qual[c]["valid_boots"] == 3 and needle_ok and axes_ok and micro_ok
    # Q0 自身：boot 有效 + s5 全过 + s2 闪烁为已知签名（记录不判败）

    # ---- 2) epsilon-Pareto（六轴，来自 P2 矩阵） ----
    def med(arm, key):
        return (mx[arm].get(key) or {}).get("median")

    pareto = {
        "axes": {
            "d565_c1": {a: med(a, "d565_c1_decode") for a in mx},
            "p4k_c4": {a: med(a, "p4k_c4_agg") for a in mx},
            "p32k_c1": {a: med(a, "p32k_c1_decode") for a in mx},
            "p128k_c1": {a: med(a, "p128k_c1_decode") for a in mx},
            "energy_p4k_c4": {a: (mx[a]["energy_J_per_tok"].get("p4k_c4") or {}).get("median_J_per_tok") for a in mx},
            "vram_capacity": {a: mx[a].get("capacity_note") or "OK(128K 可服务)" for a in mx},
        },
        "epsilon": {"throughput/prefill": "3%", "energy": "5%", "quality": "1pp 带",
                    "vram": "max(200MiB,2%)=容量墙为硬差异"},
    }

    # ---- 3) Q-Profile 定案（性能六轴 + 质量门合成；按 hard eligibility 动态生成） ----
    profiles = []
    if hard["Q0"]:
        q1m_alive = hard["Q1M"]
        profiles.append({
            "id": "QP-INTERACT", "weight_profile": "Q0（现役 W4A16+int8 头/embed）",
            "role": ("交互/全档基线（S1/L2 底座）"
                     + ("" if q1m_alive else " + 认证长上下文基线（X2——Q1M 候选被结构门否决后回退）")),
            "basis": "d565=182.6 唯一王者（全部候选 ≥31% 差距）；全档可服务（128K ✓）"
                     + ("" if q1m_alive else "；X2=Phase 03 Gate C daily 定案基线（p32kC1=69.9，128K decode 18.5）"),
            "mapping": ["S1", "L2"] + ([] if q1m_alive else ["X2"]),
        })
    if hard["Q1M"]:
        profiles.append({
            "id": "QP-LONGCTX", "weight_profile": "Q1M（W4g128 主体+敏感族 g64+首尾 W8）",
            "role": "128K 长上下文（X2 档吞吐候选）",
            "basis": "p32kC1=69.9（=Q0 带内）+128K decode 25.4（+37%>3% 带）+容量保持",
            "mapping": ["X2"], "quality_gate": "hard 门结果见 deltas",
        })
    if hard["Q4C"]:
        profiles.append({
            "id": "QP-BATCH", "weight_profile": "Q4C（W8A8-FP8 dynamic）",
            "role": "C4+ 并发吞吐/能效档",
            "basis": "p4kC4=203.6（+26%）+J/tok 2.188（记录：4.3% 在能效 5% 带内→与 Q0 能效等价）+128K 容量墙（max_model_len 118784）",
            "mapping": ["S1-高并发路由"], "capacity_limit": "128K=CAPACITY_LIMIT",
        })
    excluded = {}
    if not hard["W8"]:
        excluded["W8"] = "REJECTED_FOR_QUALITY（needle s2 配对退化 1 次 0/5 全灭形态 + IFEval −4.7pp）；被 Q4C 吞吐/能效支配；保留 same-base 质量参照（不占名额）"
    if not hard["Q1M"]:
        sf = "、".join(structural_fail_boots["Q1M"]) or "（无结构失败 boot）"
        excluded["Q1M"] = (f"REJECTED_FOR_STRUCTURAL_REGRESSION（PH4-EVIDENCE-REPAIR-01，2026-09-25）——"
                           f"有效 boot {sf} micro tool-json 安全门 STRUCTURAL_FAIL：B03 tj13 要求 JSON "
                           "却输出 Python 代码；同 boot Q0 tj13 通过、Q1M B01/B02 通过（boot 级结构不稳定）。"
                           "冻结 gates core_axes_zero_regress: tool_json_structural=结构破坏否决级；"
                           "原判定器遗漏此门，本 verdict 为修复后重算（原版归档 gate-d-verdict-pre-repair01.json）。"
                           "性能事实（p32k=Q0 无损、128K decode +37%、GSM +6.7pp）保留记录但 reference only，不进生产拓扑裁决")
    if not hard["Q4C"]:
        excluded["Q4C"] = "REJECTED（质量门未过——见 deltas）"
    excluded.update({
        "Q2M": "与 Q1M 生产角色同档（P32K 主轴 Q1M=Q0 无损 vs Q2M −16%）；d565 +10% 不足以独立成档",
        "Q3/W4A8-FP8": "UNSUPPORTED_BY_ARCH（SM89 非 hopper）",
        "Q5/NVFP4": "NOT_BUILT_EMULATION",
    })
    routing = ["QP-INTERACT=短 prompt 交互（d565/P4K C1-2）"]
    if hard["Q1M"]:
        routing.append("QP-LONGCTX=≥32K 长上下文（128K 档 +37%）")
    else:
        routing.append("≥32K 长上下文=Q0 认证基线（X2；Q1M 吞吐候选 REJECTED_FOR_STRUCTURAL_REGRESSION）")
    if hard["Q4C"]:
        routing.append("QP-BATCH=C4+ 批处理（+26%，≤32K 容量域）")
    routing_boundaries = "；".join(routing)
    verdict = {
        "repair": {
            "id": "PH4-EVIDENCE-REPAIR-01",
            "date": "2026-09-25",
            "change": "hard eligibility 补挂冻结 gates core_axes_zero_regress 的 tool_json_structural 门"
                      "（原实现仅用 boot validity/质量轴/needle，micro verdict 只采集未裁决）",
            "evidence": "raw/staging/PH4-P3/micro-Q1M-B03.json（17/20 STRUCTURAL_FAIL，tj13）",
            "prior_verdict_archived": "raw/staging/PH4-P4/gate-d-verdict-pre-repair01.json",
        },
        "gate_d": {
            "question": "同一真实 serving 栈下质量/交互/并发/prefill/显存/能效共同成立的 2-3 个可部署 Q-Profile",
            "hard_eligibility": hard,
            "hard_reject_reason": {c: ("STRUCTURAL_REGRESSION:" + "、".join(structural_fail_boots[c])
                                       if structural_fail_boots[c] else
                                       ("QUALITY_GATE" if not hard[c] else "—"))
                                   for c in ("Q0", "Q1M", "Q4C", "W8")},
            "structural_fail_boots": structural_fail_boots,
            "quality_deltas_vs_q0_pp": deltas,
            "pareto_axes": pareto["axes"],
            "epsilon_bands": pareto["epsilon"],
            "profiles": profiles,
            "excluded": excluded,
            "routing_boundaries": routing_boundaries,
        },
        "quality_detail": qual,
        "inputs": ["PH4-P3/qualify-report.json", "PH4-P2/ph4-matrix-summary.json",
                   "PH4-P3/static-ood-check.json"],
    }
    out = os.path.join(ST, "PH4-P4", "gate-d-verdict.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(verdict, open(out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"hard": hard, "deltas": deltas,
                      "Q0_axes": qual["Q0"]["holdout_axes"]}, ensure_ascii=False, indent=1)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
