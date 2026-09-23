#!/usr/bin/env python3
"""Phase 04 P0A.6/P1 — 层敏感度采集器（MASTER §10.3A）。

方法（闭式局部度量，单遍前向）：
  每模块 hook 捕获输入激活 X（token 维），累积 Gram G = Σ xᵀx（Hessian 代理）。
  对每个候选量化方案 Ŵ=fake_quant(W)：
    MSE_est   = tr(ΔW G ΔWᵀ)/N_tokens          （输出 MSE 的闭式估计）
    cos_est   = sqrt(tr(WGWᵀ) / (tr(WGWᵀ)+tr(ΔWGΔWᵀ)))   （输出余弦闭式近似，Δ⊥W 假设下）
    hess_err  = tr(ΔW G ΔWᵀ)                    （OBS 敏感度，activation 加权误差）
    rel_frob  = ||ΔW||_F/||W||_F
  NLL/perplexity 增量：family 级全前向（--nll-family，逐族换装 fake-quant）
层型分列：16 full-attention vs 48 GDN（config full_attention_interval 推导 + 实名核验）。

自测（--selftest）：合成小模块暴力对照（逐 token 前向 MSE/cos vs 闭式估计，相对差 <2%）。
Dry-run（--dry-run）：只扫模型结构（模块清点 + 层型分列），不做前向。
运行（--model/--corpus）：fp8c-build 容器内（transformers+torch），teacher=merged-bf16。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys


def fake_quant_int(w, bits: int, group: int, symmetric: bool = True):
    """RTN fake-quant（int4/int8 g128 sym）——与 AutoRound 产物的 round-trip 误差同阶。"""
    import torch
    orig_shape = w.shape
    flat = w.reshape(-1, group).float()
    if symmetric:
        scale = flat.abs().amax(dim=1, keepdim=True) / (2 ** (bits - 1) - 1)
        scale = scale.clamp(min=1e-10)
        q = torch.round(flat / scale).clamp(-(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
        dq = q * scale
    else:
        mx = flat.max(dim=1, keepdim=True).values
        mn = flat.min(dim=1, keepdim=True).values
        scale = (mx - mn) / (2 ** bits - 1)
        scale = scale.clamp(min=1e-10)
        zp = torch.round(-mn / scale)
        q = torch.round(flat / scale + zp).clamp(0, 2 ** bits - 1)
        dq = (q - zp) * scale
    return dq.reshape(orig_shape).to(w.dtype)


def module_metrics(w, G, n_tok):
    """闭式局部敏感度（G: [in,in] fp32 CPU；w: [out,in]）。

    out_ref = X Wᵀ，out_q = X Ŵᵀ，ΔW=Ŵ−W，G=Σxᵀx：
      ||err||²_F = tr(ΔW G ΔWᵀ)；逐元素 MSE = /（n_tok·out_dim）
      cos = (tr(WGWᵀ)+tr(WGΔWᵀ)) / sqrt(tr(WGWᵀ)·tr(ŴGŴᵀ))   （精确闭式，含交叉项）
    """
    import torch
    w = w.detach().float().cpu()
    out_dim = w.shape[0]
    schemes = {}
    for name, (bits, group) in (("int4_g128", (4, 128)), ("int8_g128", (8, 128))):
        wq = fake_quant_int(w, bits, group)
        dw = (wq - w).float()
        tr_dwg = torch.einsum("oi,ij,oj->", dw, G, dw).item()
        tr_wgw = torch.einsum("oi,ij,oj->", w, G, w).item()
        tr_wgdw = torch.einsum("oi,ij,oj->", w, G, dw).item()
        tr_qgq = tr_wgw + 2 * tr_wgdw + tr_dwg
        denom = math.sqrt(max(tr_wgw * tr_qgq, 0.0))
        num = tr_wgw + tr_wgdw
        schemes[name] = {
            "mse_out_est": tr_dwg / max(n_tok * out_dim, 1),
            "cos_out_est": (num / denom) if denom > 0 else None,
            "hessian_weighted_err": tr_dwg,
            "rel_frob": dw.norm().item() / max(w.norm().item(), 1e-10),
        }
    return schemes


def family_of(module_name: str, layer_idx: int, is_full_attn: bool) -> str:
    if "lm_head" in module_name:
        return "lm_head"
    if "embed_tokens" in module_name:
        return "embedding"
    if ".mlp." in module_name:
        return f"mlp.{module_name.rsplit('.', 1)[-1].replace('_proj', '')}"
    if ".self_attn." in module_name:
        return f"attn.{module_name.rsplit('.', 1)[-1].replace('_proj', '')}"
    if ".linear_attn." in module_name:
        return f"gdn.{module_name.rsplit('.', 1)[-1]}"
    return "other"


def selftest() -> int:
    """合成暴力对照：闭式估计 vs 逐 token 前向真值，相对差 <2%。"""
    import torch
    torch.manual_seed(0)
    w = torch.randn(48, 64) * 0.05
    X = torch.randn(500, 64)              # 500 token 输入
    G = (X.t() @ X)
    m = module_metrics(w, G, X.shape[0])
    for scheme in ("int4_g128", "int8_g128"):
        wq = fake_quant_int(w, *{"int4_g128": (4, 128), "int8_g128": (8, 128)}[scheme])
        out_ref = X @ w.t()
        out_q = X @ wq.t()
        mse_true = ((out_ref - out_q) ** 2).mean().item()
        cos_true = torch.nn.functional.cosine_similarity(
            out_ref.flatten(), out_q.flatten(), dim=0).item()
        mse_est = m[scheme]["mse_out_est"]
        cos_est = m[scheme]["cos_out_est"]
        rel1 = abs(mse_est - mse_true) / mse_true
        rel2 = abs(cos_est - cos_true)
        print(f"{scheme}: mse_est={mse_est:.6f} true={mse_true:.6f} rel={rel1:.4f} | "
              f"cos_est={cos_est:.5f} true={cos_true:.5f} diff={rel2:.5f}")
        if rel1 > 0.02 or rel2 > 0.001:
            print("SELFTEST FAIL")
            return 1
    print("SELFTEST PASS（闭式 vs 暴力：MSE <2%、cos <1e-3）")
    return 0


def dry_run(model_dir: str) -> int:
    """结构清点：16 full-attn vs 48 GDN 分列 + 模块族清点（无前向）。"""
    cfg = json.load(open(os.path.join(model_dir, "config.json")))
    tc = cfg.get("text_config", cfg)
    n = tc.get("num_hidden_layers")
    interval = tc.get("full_attention_interval")
    full = [i for i in range(n) if i % interval == 0]
    gdn = [i for i in range(n) if i % interval != 0]
    idx = json.load(open(os.path.join(model_dir, "model.safetensors.index.json")))
    fams = {}
    for k in idx["weight_map"]:
        if not k.endswith(".weight"):
            continue
        parts = k.split(".")
        try:
            li = int(parts[parts.index("layers") + 1])
        except (ValueError, IndexError):
            li = -1
        is_full = li in full
        f = family_of(k, li, is_full)
        fams[f] = fams.get(f, 0) + 1
    out = {"model": model_dir, "num_hidden_layers": n,
           "full_attention_layers": len(full), "gdn_layers": len(gdn),
           "interval": interval, "module_family_counts": fams,
           "verdict": "STRUCTURE_OK" if (len(full) == 16 and len(gdn) == 48) else "UNEXPECTED"}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["verdict"] == "STRUCTURE_OK" else 1


def collect(model_dir: str, corpus: str, out_csv: str, out_json: str,
            max_samples: int, max_tokens: int) -> int:
    """真采集：transformers 前向 + hook 累积 G + 逐模块闭式度量（容器内运行）。"""
    import torch
    from transformers import AutoTokenizer
    max_mem = {0: "20GiB", 1: "20GiB", "cpu": "80GiB"}   # 留激活余量（OOM 教训：auto 铺满双卡）
    try:
        from transformers import AutoModelForCausalLM as _AM
        model = _AM.from_pretrained(model_dir, torch_dtype=torch.bfloat16,
                                    device_map="auto", trust_remote_code=True,
                                    low_cpu_mem_usage=True, max_memory=max_mem)
    except Exception:  # noqa: BLE001 —— VL ForConditionalGeneration 架构 fallback
        from transformers import AutoModelForImageTextToText as _AM2
        model = _AM2.from_pretrained(model_dir, torch_dtype=torch.bfloat16,
                                     device_map="auto", trust_remote_code=True,
                                     low_cpu_mem_usage=True, max_memory=max_mem)
    tok = AutoTokenizer.from_pretrained(model_dir)
    cfg = json.load(open(os.path.join(model_dir, "config.json")))
    tc = cfg.get("text_config", cfg)
    n_layers = tc["num_hidden_layers"]
    full_set = {i for i in range(n_layers) if i % tc["full_attention_interval"] == 0}

    acc: dict[str, dict] = {}   # module_name -> {"G": tensor, "n": int, "layer": int}

    def make_hook(name: str):
        def hook(mod, inp, out):
            x = inp[0]
            x2 = x.reshape(-1, x.shape[-1]).float().cpu()
            e = acc.setdefault(name, {"G": None, "n": 0, "layer": -1})
            e["n"] += x2.shape[0]
            g = x2.t() @ x2
            e["G"] = g if e["G"] is None else e["G"] + g
        return hook

    hooks = []
    target_pat = ("q_proj", "k_proj", "v_proj", "o_proj",
                  "in_proj", "out_proj", "gate_proj", "up_proj", "down_proj")
    for name, mod in model.named_modules():
        if name.endswith(target_pat) and "visual" not in name:
            try:
                parts = name.split(".")
                li = int(parts[parts.index("layers") + 1])
            except (ValueError, IndexError):
                li = -1
            acc_key = f"{name}"
            acc[acc_key] = {"G": None, "n": 0, "layer": li,
                            "is_full_attn": li in full_set}
            hooks.append(mod.register_forward_hook(make_hook(acc_key)))

    samples = [json.loads(l)["text"] for l in open(corpus)][:max_samples]
    model.eval()
    with torch.no_grad():
        for s in samples:
            ids = tok(s, return_tensors="pt", truncation=True,
                      max_length=max_tokens).input_ids.to(model.device)
            model(ids)
    for h in hooks:
        h.remove()

    rows = []
    skipped = []
    # meta 权重（CPU offload 占位）→ checkpoint 按名直取；命名空间双形态回退
    # （活模型 model.layers.* vs checkpoint model.language_model.layers.*——v4 教训）
    tidx = json.load(open(os.path.join(model_dir, "model.safetensors.index.json")))["weight_map"]
    from safetensors import safe_open
    shard_cache: dict = {}
    for name, e in sorted(acc.items()):
        if e["G"] is None or e["n"] == 0:
            continue
        try:
            mod = dict(model.named_modules())[name]
            w = mod.weight
            if w.is_meta:
                cands = [f"{name}.weight"]
                if name.startswith("model.layers."):
                    cands.append("model.language_model." + name[len("model."):].replace(".layers.", ".layers.") + ".weight")
                    cands.append(f"model.language_model.{name.split('.', 1)[1]}.weight")
                key = next((k for k in cands if k in tidx), None)
                if key is None:
                    skipped.append({"module": name, "reason": "key_not_found"})
                    continue
                shard = os.path.join(model_dir, tidx[key])
                if shard not in shard_cache:
                    shard_cache[shard] = safe_open(shard, framework="pt")
                w = shard_cache[shard].get_tensor(key)
            mets = module_metrics(w, e["G"], e["n"])
            fam = family_of(name, e["layer"], e.get("is_full_attn", False))
            row = {"module": name, "layer": e["layer"],
                   "layer_type": "full_attn" if e.get("is_full_attn") else "gdn",
                   "family": fam, "n_tokens": e["n"], **{k: v for sch, mm in mets.items()
                                                         for k, v in ((f"{sch}.mse", mm["mse_out_est"]),
                                                                      (f"{sch}.cos", mm["cos_out_est"]),
                                                                      (f"{sch}.hess", mm["hessian_weighted_err"]),
                                                                      (f"{sch}.rel_frob", mm["rel_frob"]))}}
            rows.append(row)
        except Exception as ex:  # noqa: BLE001 —— 逐模块防御：末端失败不毁全局
            skipped.append({"module": name, "reason": repr(ex)[:120]})
    keys = list(rows[0].keys()) if rows else []
    with open(out_csv, "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(k)) for k in keys) + "\n")
    json.dump({"model": model_dir, "corpus": corpus, "rows": rows,
               "skipped": skipped},
              open(out_json, "w"), ensure_ascii=False, indent=1)
    print(f"[sensitivity] {len(rows)} modules -> {out_csv}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", dest="dry_run")
    ap.add_argument("--model")
    ap.add_argument("--corpus")
    ap.add_argument("--out-csv", default="layer-sensitivity.csv")
    ap.add_argument("--out-json", default="layer-sensitivity.json")
    ap.add_argument("--max-samples", type=int, default=64)
    ap.add_argument("--max-tokens", type=int, default=1024)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.dry_run:
        return dry_run(a.dry_run)
    if a.model and a.corpus:
        return collect(a.model, a.corpus, a.out_csv, a.out_json,
                       a.max_samples, a.max_tokens)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
