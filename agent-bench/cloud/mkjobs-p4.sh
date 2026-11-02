#!/usr/bin/env bash
# Emit the P4 queue jobs: the P1-P3 null on a second model family (gpt-oss-120b).
#
#   bash mkjobs-p4.sh <public-ip> <publish-job-number> [outdir=./p4-jobs] [first-number]
#
#   <n>   download+smoke   pull repo, hf-download gpt-oss-120b, 2-task graded smoke (vLLM parser flags, Blackwell MXFP4)
#   p4-gptoss-s15        A x3 (full attention) and B-hard x3 (recency, hard 32K) on the stuck-15
#   p4-gptoss-150        A150 and B150-hard on verified150, 8 agents  -> does retention matter on a second family?
set -uo pipefail
IP=${1:?public ip}; PUB=${2:?publish job number}; OUT=${3:-./p4-jobs}; n=${4:-$((PUB+1))}
mkdir -p "$OUT"
SSHLINE="SSH=\"ssh -i \$HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=720 -o ConnectTimeout=20 bangchickenbang@$IP\""
RB='CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:\$PATH HF_HOME=\$HOME/hf-cache ~/venvs/agent/bin/python run_bench_linux.py --model gptoss120b'
SMOKE=$n
cat > "$OUT/$n-p4-gptoss-smoke.sh" <<EOF
#!/usr/bin/env bash
# P4: fetch gpt-oss-120b (~63 GB MXFP4) and run a 2-task graded smoke on it. Gate for the matrix.
# after: $PUB
set -uo pipefail
$SSHLINE
\$SSH "bash -lc 'cd ~/candle-bench && git pull -q --ff-only && git log --oneline -1 && HF_HOME=\\\$HOME/hf-cache ~/venvs/vllm/bin/hf download openai/gpt-oss-120b >/dev/null && echo model-ok && df -h / | tail -1 && cd agent-bench/cloud && $RB --backend vllm --max-model-len 65536 --tasks 2 --workers 1 --seed 1 --label p4-smoke'"
rc=\$?; echo "P4 SMOKE DONE (exit \$rc)"; exit \$rc
EOF
chmod +x "$OUT/$n-p4-gptoss-smoke.sh"; echo "$OUT/$n-p4-gptoss-smoke.sh"; n=$((n+1))
job() {  # job <name> <group> <keep:yes|no> <args...>
  local name=$1 group=$2 keep=$3; shift 3; local f="$OUT/$n-$name.sh" k=""; [ "$keep" = yes ] && k="--keep-backend"
  { echo '#!/usr/bin/env bash'; echo "# P4: $name"; echo "# after: $SMOKE"; echo "# group: $group"; echo "# on-fail: pause-group"
    echo 'set -uo pipefail'; echo "$SSHLINE"
    echo "\$SSH \"bash -lc 'cd ~/candle-bench/agent-bench/cloud && $RB $* $k'\""
    echo 'rc=$?; echo "'"$name"' DONE (exit $rc)"; exit $rc'; } > "$f"; chmod +x "$f"; echo "$f"; n=$((n+1))
}
S15='--tasks-file ../stuck15.txt --workers 4'
for s in 1 2 3; do job "p4-A-s$s" p4-gptoss-s15 yes "--backend vllm --max-model-len 131072 --policy none $S15 --seed $s --label p4-A-s$s"; done
for s in 1 2 3; do job "p4-Bhard-s$s" p4-gptoss-s15 yes "--backend vllm --max-model-len 65536 --policy recency --budget-tokens 32768 --clip-recent $S15 --seed $s --label p4-Bhard-s$s"; done
V='--dataset verified --tasks-file ../verified150.txt --workers 8'
job "p4-A150" p4-gptoss-150 yes "--backend vllm --max-model-len 131072 --policy none $V --seed 1 --label p4-A150"
job "p4-B150hard" p4-gptoss-150 no "--backend vllm --max-model-len 65536 --policy recency --budget-tokens 32768 --clip-recent $V --seed 1 --label p4-B150hard"
echo "-- $(ls "$OUT" | wc -l) jobs in $OUT"
