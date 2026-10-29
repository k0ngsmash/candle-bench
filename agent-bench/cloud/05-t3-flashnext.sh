#!/usr/bin/env bash
# T3: the Flash-Next gate. Builds the stock Flash-Next model (no 35B switch) and tries to serve it.
# On the 4090 this died with CUDA_ERROR_ALREADY_MAPPED at the MoE live-table step; on 96 GB a clean
# start means that was the 24 GB ceiling, a repeat failure means a real bug to capture.
#   bash 05-t3-flashnext.sh
set -uo pipefail
cd "$(dirname "$0")"
PY=~/venvs/agent/bin/python
WS="${WS:-$HOME/zend-ws}"
if [ ! -x bin/zend-winflashnext ]; then
  echo "== building Flash-Next binary"
  MODEL=flashnext bash 02-build-zend.sh 32768
fi
echo "== running a 2-task gate on Flash-Next (watch for ALREADY_MAPPED in the run's zend.out)"
ZEND_BIN="bin/zend-winflashnext" ZEND_WS="$WS" "$PY" run_bench_linux.py \
  --backend zend --tasks 2 --workers 1 --label t3-flashnext --no-eval \
  && echo "T3: Flash-Next SERVED on 96 GB - the 4090 failure was the 24 GB ceiling, not a bug." \
  || echo "T3: Flash-Next did NOT serve - inspect ../runs/*t3-flashnext*/zend.out; if ALREADY_MAPPED, it is a real bug - capture the operands with the tensor-assert harness."
