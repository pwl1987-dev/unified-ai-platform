#!/usr/bin/env bash
# ph5_direct_chain.sh — Phase 05 direct 轨 cell 链（单 backend 直连，无 router）
# 用法: ph5_direct_chain.sh <role:tp1|tp2> <staging_rel_dir>
# cell 集（gates-phase05 screen_p1 direct 参照 + debt cells）：
#   tp1 (T1 形制 @36864/MS4): D565-C1 F512×3 | P32K-C1 NS×3 | P4K-C4 NS×3(=TP1-C4 debt)
#   tp2 (T2 形制 @131072/MS2): D565-C1 F512×3 | P32K-C1 NS×3 | P128KT-C1 NS×3
set -uo pipefail
ROLE=${1:?role}; ST=${2:?staging dir}
HERE="$(cd "$(dirname "$0")" && pwd)"
NG="$(dirname "$HERE")"
PY=/data/tools/vllm29-env/bin/python
SBX=/data/sandbox/nextgen-20260917
mkdir -p "$NG/raw/staging/$ST"

if [[ $ROLE == tp1 ]]; then
  PORT=19713; TP=1; MS=4; UUIDS="GPU-30776c79-cd65-60d6-4b56-69c9b6979449"
  TAG=ph5-smoke-tp1-36864; PREFIX=V29-PH5-T1F-TP1
else
  PORT=19711; TP=2; MS=2; UUIDS="GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e"
  TAG=ph5-smoke-tp2-131072; PREFIX=V29-PH5-T2F-TP2
fi
SPID=$(cat "$SBX/log-$TAG/server.pid"); SPGID=$(cat "$SBX/log-$TAG/server.pgid")

cell () {  # cell <suffix> <fixture> <modekey> <maxtok> <conc> <reps>
  local suf=$1 fx=$2 mk=$3 mt=$4 cc=$5 rp=$6
  echo "[cell] $PREFIX-$suf fixture=$fx mode=$mk mt=$mt C=$cc reps=$rp"
  "$PY" "$HERE/run_arm.py" --api "http://127.0.0.1:$PORT/v1" --port "$PORT" --tp "$TP" --ms "$MS" \
    --gpu-uuids "$UUIDS" --server-pid "$SPID" --server-pgid "$SPGID" \
    --tag "$TAG" --exp-prefix "$PREFIX-$suf" \
    --runs "$mk:$rp" --fixture "$fx" --max-tokens "$mt" --concurrency "$cc" 2>&1 | tail -3
}

if [[ $ROLE == tp1 ]]; then
  cell C1-L0565-F512 d565 f512 512 1 3
  cell C1-L032K-NS   p32k ns 256 1 3
  cell C4-L004K-NS   p4k  ns 256 4 3   # TP1-C4 debt（Phase02 移交）
else
  cell C1-L0565-F512 d565    f512 512 1 3
  cell C1-L032K-NS   p32k    ns 256 1 3
  cell C1-L128KT-NS  p128kt  ns 256 1 3
fi
echo "[$ROLE direct chain] DONE"
