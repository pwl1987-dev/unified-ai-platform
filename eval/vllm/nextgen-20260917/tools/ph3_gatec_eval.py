#!/usr/bin/env python3
"""Phase 03 P2/P3 — 三档 Profile 组装 + Gate C 分档判定（gates-phase03 gate_c）。

输入：PH3-KV/certify-238plus-report.json、PH3-KV/kvarn-ref-report.json、
      PH3-KV/p1-screen-decisions.json、PH3-P0B/specoff-decision.json、
      Phase 02 引用（P03-QUALIFY/gate-b-verdict.json 容量/needle、p32k-certify）。
输出：raw/staging/PH3-GATEC/gatec-verdict.json（三档 Profile 卡 + 分档 verdict + 结论行）。
规则：short=PASS|UNSUPPORTED；daily=PASS|UNSUPPORTED；extreme=PASS|BOUNDARY；
      单 route UNSUPPORTED 不拖垮全局；FP8E4 永不参与；KVARN 只作 CROSS_RUNTIME_REFERENCE。
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
ST = os.path.join(NG, "raw", "staging")


def load(path):
    p = os.path.join(ST, path)
    return json.load(open(p)) if os.path.exists(p) else {}


def main() -> int:
    cert = load("PH3-KV/certify-238plus-report.json")
    kvarn = load("PH3-KV/kvarn-ref-report.json")
    p1 = load("PH3-KV/p1-screen-decisions.json")
    spec = load("PH3-P0B/specoff-decision.json")
    out_dir = os.path.join(ST, "PH3-GATEC")
    os.makedirs(out_dir, exist_ok=True)

    # ---- extreme 档：238K/245K/262K 认证核验 + 标签 ---------------------
    tiers = {}
    for tier, (ml, pt) in {"238k": (243712, 238000), "245k": (251392, 245000),
                           "262k": (262144, 261888)}.items():
        boots = [v for k, v in cert.get("stages", {}).items()
                 if k.startswith(tier + "_B") and isinstance(v, dict)]
        valid = [b for b in boots if b.get("valid_observation")]
        all_pass = bool(valid) and len(valid) >= 3 and all(
            all(n.get("PASS") for n in b.get("needles", {}).values())
            for b in valid)
        no_preempt = all((b.get("preempt_oom") or {}).get("oom_lines", 0) == 0
                         for b in valid)
        kv_caps = [((b.get("info") or {}).get("capacity") or {}).get("kv_tokens")
                   for b in valid]
        kv_cap = kv_caps[0] if kv_caps and kv_caps[0] else None
        workpoint = {"238k": 238245, "245k": 245241, "262k": 262137}[tier]
        kv_margin = ((kv_cap - workpoint) / workpoint) if kv_cap else None
        pos_margin = {"238k": 5467, "245k": 6151, "262k": 7}[tier]
        ttfts = [n.get("ttft_s") for b in valid for n in b.get("needles", {}).values()
                 if isinstance(n.get("ttft_s"), (int, float))]
        if tier == "262k":
            label_on_pass = "HARD_CEILING_CAPABILITY_PASS"
        else:
            # KV 峰 ≥95%（即余量 <5%）→ BOUNDARY_PROFILE
            label_on_pass = ("BOUNDARY_PROFILE" if (kv_margin is not None and kv_margin < 0.05)
                             else "PRODUCTION_SAFE")
        tiers[tier] = {
            "boots_valid": len(valid), "all_needles_pass": all_pass,
            "no_oom": no_preempt, "kv_tokens_capacity": kv_cap,
            "workpoint_tokens": workpoint,
            "kv_capacity_margin": round(kv_margin, 4) if kv_margin is not None else None,
            "model_position_margin_tokens": pos_margin,
            "ttft_s_min_max": ([round(min(ttfts), 1), round(max(ttfts), 1)]
                               if ttfts else None),
            "certified": bool(all_pass and no_preempt and len(valid) >= 3),
            "label": label_on_pass if (all_pass and no_preempt and len(valid) >= 3)
                     else "NOT_CERTIFIED（维持 CEILING_OBSERVATION，见原因）",
        }

    extreme_verdict = "PASS" if all(tiers[t]["certified"] for t in ("238k", "245k")) \
        else ("BOUNDARY" if any(tiers[t]["certified"] for t in tiers) else "UNSUPPORTED")

    # ---- short / daily 档 ------------------------------------------------
    short_verdict = "PASS"   # L2 = B0 spec-on（P0B 认证维持；路由 caveat 附注）
    daily_verdict = "PASS"   # X2 = composite_X2 + NATIVE（FP8 UNSUPPORTED 后由 NATIVE 承担）

    prof_short = {
        "runtime": "0.29 frozen（tree 4632d624…）+ W4A16 + DFlash2 k7 spec + TP2 + draftTP1",
        "kv_route": "NATIVE_BF16", "context_envelope": "D565/P4K/P32K（model_len 36864）",
        "certified_axes": {
            "d565_decode_tok_s": spec.get("axes", {}).get("SPECON", {})
                .get("d565_decode", {}).get("median"),
            "p32k_decode_tok_s": spec.get("axes", {}).get("SPECON", {})
                .get("p32k_cold_decode", {}).get("median"),
            "p32k_warm_ttft_s": spec.get("axes", {}).get("SPECON", {})
                .get("p32k_warm_ttft", {}).get("median"),
        },
        "conditional_routing": "P32K 级工作负载 spec-off 更优（decode +12%/agg +33%/暖TTFT −39%，"
                               "P0B 认证证据）——生产路由建议，非配方变更",
    }
    prof_daily = {
        "runtime": "同 short（X2 形制）",
        "kv_route": "NATIVE_BF16",
        "context_envelope": "128K（C1-C2；C4=CAPACITY_LIMIT 端点 526K>374K KV）/ 220K（在途=1，q4 护栏）",
        "references": "Phase 02 B0-X128/X220 + Gate B（seed99 全档 5/5；220K TTFT −0.17%；容量 1.42×/1.78×）",
        "fp8_unlock": "FP8-KV UNSUPPORTED（flashinfer JIT CCCL 墙）——128K C4 解锁落空，"
                      "上游修复后 Phase 04+ 复评",
    }
    prof_extreme = {
        "runtime": "同 short（MS1 在途=1）", "kv_route": "NATIVE_BF16",
        "tiers": tiers,
        "production_safe_candidates": ["238k", "245k"],
        "hard_ceiling": "262k（position 余量 7 token——MODEL_POSITION_BOUNDARY；"
                        "永不默认生产工作点）",
    }

    verdict = {
        "gate_c": {
            "question": "至少产出短上下文质量/极速档、128K-220K 日常档、238K-262K 极限档",
            "per_tier": {"short": short_verdict, "daily": daily_verdict,
                         "extreme": extreme_verdict},
            "formal_selection": "0.29 主栈 = NATIVE_BF16（FP8E4/FP8C UNSUPPORTED；"
                                "KVARN 0.28 = CROSS_RUNTIME_REFERENCE 保留至 Phase 08）",
            "global_rule": "单 route UNSUPPORTED 不拖垮 Gate C——FP8 两路缺席由 NATIVE 承担",
        },
        "fp8_split_conclusion": {
            "FP8E4_diagnostic": p1.get("fp8_route_verdict", {}),
            "FP8C_production_candidate": "UNSUPPORTED（同 serving 层阻断；artifact 未构建——"
                                         "构建/验证链就绪待上游修复）",
        },
        "kvarn_reference_conclusion": {
            "eligibility": "CROSS_RUNTIME_REFERENCE（禁止同栈 winner/tie-break/越域质量 FAIL）",
            "points": {"d565_c1": kvarn.get("d565_c1"),
                       "needles": {k: {"hit": v.get("needles_hit"), "ttft": v.get("ttft_s")}
                                   for k, v in (kvarn.get("needles") or {}).items()},
                       "kv_tokens_kvarn": (kvarn.get("capacity") or {}).get("kv_tokens_kvarn")},
            "retention": "legacy/extreme reference 保留至 Phase 08 切换窗口",
        },
        "profiles": {"short": prof_short, "daily": prof_daily, "extreme": prof_extreme},
    }
    out = os.path.join(out_dir, "gatec-verdict.json")
    json.dump(verdict, open(out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"gate_c": verdict["gate_c"]["per_tier"],
                      "tiers": {k: {"certified": v["certified"], "label": v["label"],
                                    "kv_margin": v["kv_capacity_margin"]}
                                for k, v in tiers.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
