#!/usr/bin/env bash
# Stage-1 candidate downloads via hf-mirror (huggingface.co blocked on this host).
# Two lanes run sequentially inside, invoked as: download-stage1.sh lane1|lane2
set -u
export HF_ENDPOINT=https://hf-mirror.com
BASE=/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/models
DL="uv run --project /data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner hf download"

lane1() {
  $DL ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf --local-dir "$BASE/ISTA-DASLab" >>"$BASE/lane1.txt" 2>&1
  $DL ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF mmproj-Qwen3.8-27B-BF16.gguf      --local-dir "$BASE/ISTA-DASLab" >>"$BASE/lane1.txt" 2>&1
  $DL ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF README.md                           --local-dir "$BASE/ISTA-DASLab" >>"$BASE/lane1.txt" 2>&1
  $DL ukisai/Swift-Qwen3.8-27B-GGUF Swift-Qwen3.8-27B-Q4_K_M.gguf              --local-dir "$BASE/ukisai-swift10" >>"$BASE/lane1.txt" 2>&1
  $DL ukisai/Swift-Qwen3.8-27B-GGUF README.md                                  --local-dir "$BASE/ukisai-swift10" >>"$BASE/lane1.txt" 2>&1
  $DL ukisai/Swift-Qwen3.8-27B-GGUF SHA256SUMS                                 --local-dir "$BASE/ukisai-swift10" >>"$BASE/lane1.txt" 2>&1
  $DL ukisai/Swift-Qwen3.8-27B-GGUF SHA256SUMS.quants                          --local-dir "$BASE/ukisai-swift10" >>"$BASE/lane1.txt" 2>&1
}
lane2() {
  $DL ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf --local-dir "$BASE/ukisai-swift15-gsq" >>"$BASE/lane2.txt" 2>&1
  for f in LICENSE NOTICE README.md RECIPE.txt SHA256SUMS release-manifest.json; do
    $DL ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF "$f" --local-dir "$BASE/ukisai-swift15-gsq" >>"$BASE/lane2.txt" 2>&1
  done
  $DL ukisai/Swift-1.5-Qwen3.8-27B-GGUF Swift-1.5-Qwen3.8-27B-Q5_K_M.gguf --local-dir "$BASE/ukisai-swift15" >>"$BASE/lane2.txt" 2>&1
  $DL ukisai/Swift-1.5-Qwen3.8-27B-GGUF Swift-1.5-Qwen3.8-27B-Q6_K.gguf   --local-dir "$BASE/ukisai-swift15" >>"$BASE/lane2.txt" 2>&1
  $DL ukisai/Swift-1.5-Qwen3.8-27B-GGUF mmproj-Swift-1.5-Qwen3.8-27B-F16.gguf --local-dir "$BASE/ukisai-swift15" >>"$BASE/lane2.txt" 2>&1
  for f in LICENSE README.md; do
    $DL ukisai/Swift-1.5-Qwen3.8-27B-GGUF "$f" --local-dir "$BASE/ukisai-swift15" >>"$BASE/lane2.txt" 2>&1
  done
}
"$1"
echo "LANE $1 DONE $(date -Is)"
