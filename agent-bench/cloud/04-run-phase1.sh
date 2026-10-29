#!/usr/bin/env bash
# Phase 1: T1 (window-at-headroom, the headline) + T2 (residency & concurrency) on one 96 GB card.
# Starts with a 2-task smoke to shake out the Linux harness port cheaply before the real runs.
#
#   bash 04-run-phase1.sh              # loop metric only (fast; no Docker scoring)
#   EVAL=1 bash 04-run-phase1.sh       # also score solves with the SWE-bench harness (needs Docker + disk)
#
# The loop metric (the headline) comes from the agent trajectories, not from scoring, so EVAL=0 still
# answers the main question. Turn EVAL=1 on once Docker + the eval images are confirmed working.
set -uo pipefail
cd "$(dirname "$0")"
PY=~/venvs/agent/bin/python
RB="run_bench_linux.py"
WS="${WS:-$HOME/zend-ws}"
TASKS="$PWD/../stuck15.txt"
EVALFLAG=""; [ "${EVAL:-0}" = "1" ] || EVALFLAG="--no-eval"
run() { echo; echo ">>> $*"; ZEND_WS="$WS" "$@"; }

echo "==== SMOKE: 2 tasks on the 32K binary (port check) ===="
ZEND_BIN="bin/zend-win32768" run "$PY" "$RB" --backend zend --tasks 2 --workers 1 --label smoke --no-eval \
  || { echo "smoke failed - fix before the real runs (see the run dir's zend.out / preflight.log)"; exit 1; }

echo; echo "==== T1: window sweep (stuck15, 1 agent, fully resident) ===="
for W in 32768 65536 131072 262144; do
  B="bin/zend-win$W"
  [ -x "$B" ] || { echo "missing $B - run 03-build-windows.sh first"; exit 1; }
  ZEND_BIN="$B" run "$PY" "$RB" --backend zend --tasks-file "$TASKS" --workers 1 --label "win$W" $EVALFLAG
done

echo; echo "==== T2: residency & concurrency (10 tasks, 32K binary) ===="
# On 96 GB the 35B is fully resident, so this isolates concurrency scaling from expert streaming.
ZEND_BIN="bin/zend-win32768" run "$PY" "$RB" --backend zend --tasks 10 --workers 1 --label conc-w1 $EVALFLAG
ZEND_BIN="bin/zend-win32768" run "$PY" "$RB" --backend zend --tasks 10 --workers 8 --label conc-w8 $EVALFLAG

echo; echo "PHASE 1 DONE - summaries under ../runs/. Loop metric is the 'Looping:' line in each summary.md."
