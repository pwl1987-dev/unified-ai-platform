#!/usr/bin/env bash
# P4-A：Gate B 补件 —— TP2 B0 形制 P32K C2(goodput 主轴) + C1(锚) ×2 boot（平台趁热，无 WARMUP 弃置）
set -uo pipefail
cd "$(dirname "$0")"
PY=/data/tools/vllm29-env/bin/python
SBX=/data/sandbox/nextgen-20260917
RUNLOG=$SBX/p4-gateb-tp2-runlog.txt

for BOOT in G1 G2; do
  # 等 GPU3+4 空
  while true; do
    FREE=$(nvidia-smi --query-gpu=uuid,memory.used --format=csv,noheader | awk -F', ' '
      $1=="GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae" {a=$2+0}
      $1=="GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e" {b=$2+0}
      END {print (a<1000 && b<1000) ? 1 : 0}')
    [ "$FREE" = "1" ] && break
    sleep 30
  done
  echo "[$(date '+%F %T')] booting GATEB-$BOOT" >> "$RUNLOG"
  rm -rf "$SBX/cache-p02-gateb$BOOT"
  VLLM_CACHE_ROOT=$SBX/cache-p02-gateb$BOOT setsid bash boot029_nextgen.sh p02-gateb$BOOT 19702 2 4 \
    --kv-dtype bfloat16 --model-len 36864 --spec 1 --patch a --nbt 2048 --k 7 >> "$RUNLOG" 2>&1
  PGID=$(cat "$SBX/log-p02-gateb$BOOT/server.pgid" 2>/dev/null || echo "")
  PID=$(cat "$SBX/log-p02-gateb$BOOT/server.pid" 2>/dev/null || echo "")
  [ -z "$PGID" ] && { echo "[$(date '+%F %T')] GATEB-$BOOT BOOT FAIL" >> "$RUNLOG"; continue; }
  # C2 goodput 主轴 ×3 + C1 锚 ×3（P32K）
  for SPEC in "C2 2" "C1 1"; do
    set -- $SPEC; CELL=$1; CONC=$2
    MODE=NS
    $PY run_arm.py --api http://127.0.0.1:19702/v1 --port 19702 --tp 2 --ms 4 \
      --gpu-uuids "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e" \
      --server-pid "$PID" --server-pgid "$PGID" --tag p02-gateb$BOOT \
      --exp-prefix "V29-T2-GATEB-KVBF16-SD7-MS4-NBT2048-L36K-$CELL-L032K" \
      --runs ns:3 --fixture p32k --max-tokens 256 --concurrency "$CONC" \
      --boot-tag "$BOOT" >> "$RUNLOG" 2>&1
    echo "[$(date '+%F %T')] GATEB-$BOOT $CELL rc=$?" >> "$RUNLOG"
  done
  # PGID 安全停（防自杀：核对非自身进程组）
  if [ "$PGID" != "$(ps -o pgid= -p $$ | tr -d ' ')" ]; then
    kill -TERM -"$PGID" 2>/dev/null; sleep 20; kill -KILL -"$PGID" 2>/dev/null
  fi
  echo "[$(date '+%F %T')] GATEB-$BOOT stopped" >> "$RUNLOG"
  sleep 5
done
touch "$SBX/p4-gateb-tp2.done"
echo "[$(date '+%F %T')] === GATEB TP2 补件完成 ===" >> "$RUNLOG"
