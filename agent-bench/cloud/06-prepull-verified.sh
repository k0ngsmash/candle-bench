#!/usr/bin/env bash
# P2 prep, run on the box: pick the Verified slice (deterministic) and pre-pull its SWE-bench docker
# images so the agent runs and the grader never spend wall-clock time downloading (keeps the
# per-task timing comparable across arms). Idempotent; safe to re-run.
#
#   bash 06-prepull-verified.sh [N=150] [SEED=0] [PARALLEL=4]
set -uo pipefail
N=${1:-150}; SEED=${2:-0}; PAR=${3:-4}
cd "$(dirname "$0")"
HF_HOME=${HF_HOME:-$HOME/hf-cache} ~/venvs/agent/bin/python pick_verified.py --n "$N" --seed "$SEED" || exit 1
LIST=../verified$N.txt
echo "== pre-pulling $(wc -l < "$LIST") images, $PAR at a time ($(date +%H:%M))"
# SWE-bench image naming: swebench/sweb.eval.x86_64.<instance id with '__' -> '_1776_'>:latest
sed 's/__/_1776_/' "$LIST" | xargs -P "$PAR" -I{} sh -c 'docker image inspect swebench/sweb.eval.x86_64.{}:latest >/dev/null 2>&1 && echo "have {}" || { docker pull -q swebench/sweb.eval.x86_64.{}:latest >/dev/null 2>&1 && echo "pulled {}" || echo "FAILED {}"; }' \
  | tee /tmp/prepull.log | awk '{n[$1]++} END {for (k in n) printf "%s=%d ", k, n[k]; print ""}'
echo "== docker disk: $(docker system df --format '{{.Type}} {{.Size}}' | head -1)   free: $(df -h / | awk 'NR==2{print $4}')   ($(date +%H:%M))"
grep -c '^FAILED' /tmp/prepull.log | xargs -I{} sh -c '[ {} -eq 0 ] && echo "PREPULL DONE" || { echo "PREPULL: {} images failed - see /tmp/prepull.log"; exit 1; }'
