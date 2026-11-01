#!/usr/bin/env bash
# Emit the P3 queue jobs. Writes job files only.
#
#   bash mkjobs-p3.sh <public-ip> <publish-job-number> [outdir=./p3-jobs] [first-number]
#
# Groups (runner directives; every job pulls the repo first and depends on the publish job):
#   p3-nothink    A-strip x3, Bsoft-strip x3 on the stuck-15: same as P1's A and B, but the agent's
#                 past reasoning_content is removed from the history. Isolates the one variable the
#                 P2 hard-cap arms changed besides size.
#   p3-verified2  B150 s2, C150 s2 (hard 32K, 8 agents): second seed; A150 (full attention) as the
#                 Verified ceiling; A150-strip: the reasoning question at n = 150.
# The last job drops --keep-backend so the engine is torn down.
set -uo pipefail
IP=${1:?public ip}; PUB=${2:?publish job number}; OUT=${3:-./p3-jobs}; n=${4:-$((PUB+1))}
mkdir -p "$OUT"
SSHLINE="SSH=\"ssh -i \$HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=720 -o ConnectTimeout=20 bangchickenbang@$IP\""
RB='CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:\$PATH HF_HOME=\$HOME/hf-cache ~/venvs/agent/bin/python run_bench_linux.py'
job() {  # job <name> <group> <keep:yes|no> <run_bench args...>
  local name=$1 group=$2 keep=$3; shift 3
  local f="$OUT/$n-$name.sh" k=""; [ "$keep" = yes ] && k="--keep-backend"
  {
    echo '#!/usr/bin/env bash'; echo "# P3: $name"; echo "# after: $PUB"; echo "# group: $group"; echo "# on-fail: pause-group"
    echo 'set -uo pipefail'; echo "$SSHLINE"
    echo "\$SSH \"bash -lc 'cd ~/candle-bench && git pull -q --ff-only && cd agent-bench/cloud && $RB $* $k'\""
    echo 'rc=$?; echo "'"$name"' DONE (exit $rc)"; exit $rc'
  } > "$f"; chmod +x "$f"; echo "$f"; n=$((n+1))
}
S15='--tasks-file ../stuck15.txt --workers 4'
REL='--policy relevance --embed-model BAAI/bge-small-en-v1.5'
for s in 1 2 3; do job "p3-Astrip-s$s" p3-nothink yes "--backend vllm --max-model-len 131072 --policy none --strip-reasoning $S15 --seed $s --label p3-Astrip-s$s"; done
for s in 1 2 3; do job "p3-Bstrip-s$s" p3-nothink yes "--backend vllm --max-model-len 65536 --policy recency --budget-tokens 32768 --strip-reasoning $S15 --seed $s --label p3-Bstrip-s$s"; done
V='--dataset verified --tasks-file ../verified150.txt --workers 8'
job "p3-B150-s2" p3-verified2 yes "--backend vllm --max-model-len 65536 --policy recency --budget-tokens 32768 --clip-recent $V --seed 2 --label p3-B150-s2"
job "p3-C150-s2" p3-verified2 yes "--backend vllm --max-model-len 65536 $REL --budget-tokens 32768 --clip-recent $V --seed 2 --label p3-C150-s2"
job "p3-A150" p3-verified2 yes "--backend vllm --max-model-len 131072 --policy none $V --seed 1 --label p3-A150"
job "p3-A150strip" p3-verified2 no "--backend vllm --max-model-len 131072 --policy none --strip-reasoning $V --seed 1 --label p3-A150strip"
echo "-- $(ls "$OUT" | wc -l) jobs in $OUT"
