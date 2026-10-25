#!/usr/bin/env bash
# The main comparison, unattended: 30 SWE-bench Lite tasks at 4 parallel agents on each engine,
# then a concurrency sweep (1 and 8 agents) on the first 10 of them. Each run is scored and
# summarised in its own folder under agent-bench/runs/. Roughly 4-6 hours.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/harness"
PY=~/venvs/agent/bin/python
run() { echo; echo "######## $*  ($(date +%H:%M))"; $PY run_bench.py "$@" --offloads 6,8,10 || echo "!! run failed: $*"; }
run --backend zend --tasks 30 --workers 4 --label main
run --backend vllm --tasks 30 --workers 4 --label main
run --backend zend --tasks 10 --workers 8 --label sweep
run --backend vllm --tasks 10 --workers 8 --label sweep
run --backend zend --tasks 10 --workers 1 --label sweep
run --backend vllm --tasks 10 --workers 1 --label sweep
echo; echo "MAIN DONE $(date +%H:%M)"
