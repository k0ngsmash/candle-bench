#!/usr/bin/env bash
# Is zend's looping caused by the context it holds? The 15 tasks where zend's agents ran out of steps,
# one agent at a time, twice on zend:
#   1. as before (zend keeps its own context, earlier reasoning included)
#   2. "fresh": every call is a new conversation, so zend rebuilds the context from the agent's history,
#      which carries answers and tool calls but not earlier reasoning - what vLLM sees.
# If (2) loops much less than (1), the held reasoning is the cause. Roughly 2-3 hours.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/harness"
PY=~/venvs/agent/bin/python
echo "######## zend, held context  ($(date +%H:%M))"
$PY run_bench.py --backend zend --tasks-file ../stuck15.txt --workers 1 --label loop-held
echo "######## zend, fresh context  ($(date +%H:%M))"
$PY run_bench.py --backend zend --tasks-file ../stuck15.txt --workers 1 --label loop-fresh --fresh-context
echo "LOOPING TEST DONE $(date +%H:%M)"
