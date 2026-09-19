#!/usr/bin/env bash
# p0b_p1_chain.sh — Phase 02 自治续跑链 v2（任意授权空闲对，不死等 3+4）
# 用户拍板（2026-09-19）：GPU0/1 生产必备禁碰；TP2 可用授权空闲池任一对，优先冻结对 3+4。
# 选对优先级：3+4（历史可比）> 2+5 > 2+6 > 2+7（GPU2 为公共成员，空闲池内）。
# 跨对代价已记录：B0 为 Phase 02 新测分母（不受影响）；唯一跨对引用 = X2-220K TTFT vs
# Layer X 104.125s（3+4 实测），标 cross-pair + topo 等价注记（全 PXB/NUMA0）。
# 铁律照旧：未知进程零触碰（只轮询显存）；GPU0/1 与 :8000 零触碰；断点续跑。
set -uo pipefail

NEXTGEN=/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917
SBX=/data/sandbox/nextgen-20260917
PY=/data/tools/vllm29-env/bin/python
RUNLOG=$SBX/p0b-p1-chain-runlog.txt
LOCK=$SBX/p0b-p1-chain.lock
DONE_MARKER=$SBX/p0b-p1-chain.done
U2=GPU-41a1986d-e745-9e40-c520-09490081fd44
U3=GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae
U4=GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e
U5=GPU-b98c4a80-4488-5d95-92a4-a8b3a9a30950
U6=GPU-30776c79-cd65-60d6-4b56-69c9b6979449
U7=GPU-5cf0f8a6-26d7-e5e3-a9f6-5d4d5211258e
DEADLINE=$(( $(date +%s) + 24*3600 ))

log() { echo "[$(date '+%F %T')] $*" | tee -a "$RUNLOG"; }

if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  log "已有实例在跑（pid=$(cat $LOCK)），退出"; exit 0
fi
echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' EXIT
[ -f "$DONE_MARKER" ] && { log "done marker 存在"; exit 0; }

gpu_used_mib() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id="$1" | tr -d ' '; }
is_free() { [ "$(gpu_used_mib "$1")" -le 100 ]; }

choose_pair() {   # 输出 "U_a,U_b" 或空
  if is_free "$U3" && is_free "$U4"; then echo "$U3,$U4"; return; fi
  for c in "$U5" "$U6" "$U7"; do
    if is_free "$U2" && is_free "$c"; then echo "$U2,$c"; return; fi
  done
  echo ""
}

pair_name() { case "$1" in "$U3,$U4") echo "3+4(frozen)";; "$U2,$U5") echo "2+5";; "$U2,$U6") echo "2+6";; "$U2,$U7") echo "2+7";; *) echo "?";; esac; }

wait_pair() {     # 阻塞直到有可用对或超时
  while :; do
    local p; p=$(choose_pair)
    [ -n "$p" ] && { echo "$p"; return 0; }
    [ "$(date +%s)" -ge "$DEADLINE" ] && return 1
    sleep 60
  done
}

mk_resolved() {   # $1=base arms json $2=out json $3=pair uuids
  "$PY" - "$1" "$2" "$3" <<'PYEOF'
import json, sys
base, out, pair = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(base))
for arm in d["arms"]:
    arm["boot"]["pair_uuids"] = pair
d["resolved_pair"] = pair
json.dump(d, open(out, "w"), ensure_ascii=False, indent=1)
PYEOF
}

busbw() {  # $1=pair uuids $2=port $3=out
  local u port outtmp
  u="$1"; port="$2"; outtmp="$3"
  CUDA_VISIBLE_DEVICES="$u" P0B_GPU_UUIDS="$u" \
    "$PY" -m torch.distributed.run --nproc_per_node=2 --master_port="$port" \
    "$NEXTGEN/tools/p0b_busbw.py" --out "$outtmp" >> "$RUNLOG" 2>&1
}

log "=== 链 v2 启动（任意授权空闲对；优先 3+4；GPU0/1 禁碰；rpg-bakeoff 零触碰）==="

# ---- 选对 ----
PAIR=$(wait_pair) || { log "24h 无可用对，退出"; exit 3; }
PNAME=$(pair_name "$PAIR")
log "选定工作对：$PNAME（$PAIR）"
echo "$PAIR" > "$SBX/p0b-pairscan/working-pair.txt"

mkdir -p "$SBX/p0b-pairscan"
nvidia-smi topo -m > "$SBX/p0b-pairscan/topo-m.txt" 2>&1
numactl --hardware > "$SBX/p0b-pairscan/numactl-h.txt" 2>&1 || true
taskset -pc $$ > "$SBX/p0b-pairscan/chain-affinity.txt" 2>/dev/null || true
log "topo/NUMA/affinity 留档完成"

# ---- 1) busbw 工作对 ----
busbw "$PAIR" 29801 "$SBX/p0b-pairscan/busbw-working.json" && log "busbw $PNAME OK" || log "busbw $PNAME FAIL（不影响 bench 半）"

# ---- 2) PAIR-bench 工作对（配对比较的工作半 + B0 前哨 boot）----
mk_resolved "$NEXTGEN/repro/p02-arms/p0b-pairs.json" "$SBX/p0b-pairs-resolved.json" "$PAIR"
cd "$NEXTGEN/tools"
"$PY" p02_screen.py --arms "$SBX/p0b-pairs-resolved.json" --only PAIR34 --boot-tag B01 \
  >> "$SBX/p0b-p1-chain-pairW.log" 2>&1 && log "PAIR-bench($PNAME) OK" || log "PAIR-bench($PNAME) FAIL"

# ---- 3) B0 三形制（同工作对；boot 前重验该对仍空闲，被抢则重选对）----
for SPEC in "B0L32 B01" "B0L32 B02" "B0L32 B03" "B0X128 B01" "B0X220 B01"; do
  set -- $SPEC; KEY=$1; BT=$2
  P=$(choose_pair); [ -z "$P" ] && { P=$(wait_pair) || { log "$KEY-$BT 无对可用，终止"; exit 4; }; }
  if [ "$P" != "$PAIR" ]; then
    log "工作对切换：$(pair_name "$PAIR") → $(pair_name "$P")（原对被占/释放波动；跨对数据将分谱记录）"
    PAIR="$P"; echo "$PAIR" > "$SBX/p0b-pairscan/working-pair.txt"
    mk_resolved "$NEXTGEN/repro/p02-arms/p1-b0-baselines.json" "$SBX/p1-b0-baselines-resolved.json" "$PAIR"
  fi
  [ -f "$SBX/p1-b0-baselines-resolved.json" ] || mk_resolved "$NEXTGEN/repro/p02-arms/p1-b0-baselines.json" "$SBX/p1-b0-baselines-resolved.json" "$PAIR"
  "$PY" p02_screen.py --arms "$SBX/p1-b0-baselines-resolved.json" --only "$KEY" --boot-tag "$BT" \
    >> "$SBX/p0b-p1-chain-$KEY.log" 2>&1 && log "$KEY-$BT OK ($(pair_name "$PAIR"))" || log "$KEY-$BT FAIL（留证）"
done

# ---- 4) 机会主义：冻结对 3+4 若已空，补配对比较另一半 ----
if is_free "$U3" && is_free "$U4"; then
  busbw "$U3,$U4" 29802 "$SBX/p0b-pairscan/busbw-pair34.json" && log "busbw 3+4 OK（对照半）" || log "busbw 3+4 FAIL"
  "$PY" p02_screen.py --arms "$NEXTGEN/repro/p02-arms/p0b-pairs.json" --only PAIR34 --boot-tag B01 \
    >> "$SBX/p0b-p1-chain-pair34.log" 2>&1 && log "PAIR34 bench OK（对照半）" || log "PAIR34 bench FAIL"
else
  log "3+4 仍被占，配对比较对照半留交互会话补（busbw-working + PAIR-bench 工作半已有）"
  echo "DEFERRED_34_BUSY" > "$SBX/p0b-pairscan/pair34-deferred.txt"
fi

nvidia-smi --query-gpu=index,memory.used --format=csv,noheader > "$SBX/p0b-pairscan/final-gpu-state.txt"
touch "$DONE_MARKER"
log "=== 链 v2 完成（工作对 $PNAME）＝busbw + PAIR-bench + B0 三形制；判定/评估留交互 ==="
