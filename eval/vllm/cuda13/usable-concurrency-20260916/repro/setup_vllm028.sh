#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV=${VENV:-/data/tools/qwen-vllm028-repro}
PYTHON=${PYTHON:-python3.12}
PATCH=${PATCH:-$HERE/../../../../../inference/vllm/build/cu130-driver580/vllm028-kvarn-dflash2-w4a16.patch}
LOCK=${LOCK:-$HERE/manifests/vllm028-packages.lock.txt}
command -v "$PYTHON" >/dev/null || { echo "missing $PYTHON" >&2; exit 2; }
command -v patch >/dev/null || { echo "missing patch(1)" >&2; exit 2; }
if ! "$PYTHON" -c 'import ensurepip' >/dev/null 2>&1; then
  echo "missing ensurepip; on Ubuntu install python3.12-venv before running this setup" >&2
  exit 2
fi
[ ! -e "$VENV" ] || { echo "refusing to overwrite existing VENV=$VENV" >&2; exit 2; }
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$LOCK"
"$VENV/bin/python" -m pip check
SP=$($VENV/bin/python - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)
patch -p1 --dry-run -d "$SP" < "$PATCH"
patch -p1 -d "$SP" < "$PATCH"
"$VENV/bin/python" - <<'PY'
import vllm
from vllm.v1.attention.backends.registry import AttentionBackendEnum
from vllm.model_executor.models.qwen3_dflash2 import CandidateSelector
print("vllm", vllm.__version__)
print("kvarn", AttentionBackendEnum.KVARN.get_class())
print("selector", CandidateSelector.__name__)
PY
