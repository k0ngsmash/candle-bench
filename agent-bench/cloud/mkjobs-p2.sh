#!/usr/bin/env bash
# Emit the P2 queue jobs for a (re)started box. Prints nothing to the box; writes job files only.
#
#   bash mkjobs-p2.sh <public-ip> [outdir=./p2-jobs] [first-number=93]
#
# Order and gating (runner directives):
#   <n>   probe+pull            resume probe, git pull, deps sanity (vllm/zend/docker/ninja/Python.h)
#   <n+1> prepull-verified      06-prepull-verified.sh (150 images; ~1 h; # after: probe)
#   E256K x3                    zend with a window that holds everything - the engine-effect control
#   Bhard x3, Chard x3          recency / relevance at a HARD 32K cap (--clip-recent)
#   B150, C150                  recency vs relevance on verified150, 8 agents, 1 seed (n=150 each)
# Every run is graded; groups pause themselves on a failure; the last job tears the engine down.
set -uo pipefail
IP=${1:?public ip}; OUT=${2:-./p2-jobs}; n=${3:-93}
mkdir -p "$OUT"
SSHLINE="SSH=\"ssh -i \$HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=720 -o ConnectTimeout=20 bangchickenbang@$IP\""
RB='CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:\$PATH HF_HOME=\$HOME/hf-cache ~/venvs/agent/bin/python run_bench_linux.py'
ZE='ZEND_WS=\$HOME/zend-ws '
job() {  # job <name> <group|-> <after|-> <keep:yes|no> <env-prefix|""> <run_bench args...>
  local name=$1 group=$2 after=$3 keep=$4 envp=$5; shift 5
  local f="$OUT/$n-$name.sh" k=""; [ "$keep" = yes ] && k="--keep-backend"
  {
    echo '#!/usr/bin/env bash'
    echo "# P2: $name"
    [ "$after" != - ] && echo "# after: $after"
    [ "$group" != - ] && { echo "# group: $group"; echo "# on-fail: pause-group"; }
    echo 'set -uo pipefail'; echo "$SSHLINE"
    echo "\$SSH \"bash -lc 'cd ~/candle-bench/agent-bench/cloud && ${envp}$RB $* $k'\""
    echo 'rc=$?; echo "'"$name"' DONE (exit $rc)"; exit $rc'
  } > "$f"; chmod +x "$f"; echo "$f"; n=$((n+1))
}
PROBE=$n
cat > "$OUT/$n-p2-probe.sh" <<EOF
#!/usr/bin/env bash
# P2 resume probe: what survived the stop, pull the harness, sanity-check every dependency the arms need.
set -uo pipefail
$SSHLINE
\$SSH 'bash -s' <<'REMOTE'
set -u
hostname; uptime; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; df -h / | tail -1
docker ps >/dev/null 2>&1 && echo docker-ok || { echo "docker NOT usable"; exit 1; }
ls ~/candle-bench/agent-bench/cloud/bin/zend-win{32768,65536,262144} >/dev/null && echo zend-bins-ok || { echo "zend binaries missing"; exit 1; }
[ -x ~/venvs/vllm/bin/vllm ] && command -v ninja >/dev/null && [ -f /usr/include/python3.12/Python.h ] && [ -f ~/.flashinfer-sampling-ok ] && echo vllm-deps-ok || { echo "vllm deps incomplete (ninja/Python.h/flashinfer marker)"; exit 1; }
cd ~/candle-bench && git pull -q --ff-only && git log --oneline -1
cd agent-bench/harness && ~/venvs/agent/bin/python test_context_policy.py | tail -1
echo "PROBE DONE"
REMOTE
EOF
chmod +x "$OUT/$n-p2-probe.sh"; echo "$OUT/$n-p2-probe.sh"; n=$((n+1))
cat > "$OUT/$n-p2-prepull.sh" <<EOF
#!/usr/bin/env bash
# P2: pick verified150 and pre-pull its docker images (~1 h). Independent of the GPU runs.
# after: $PROBE
set -uo pipefail
$SSHLINE
\$SSH "bash -lc 'cd ~/candle-bench/agent-bench/cloud && bash 06-prepull-verified.sh 150 0 4'"
rc=\$?; echo "PREPULL DONE (exit \$rc)"; exit \$rc
EOF
chmod +x "$OUT/$n-p2-prepull.sh"; echo "$OUT/$n-p2-prepull.sh"; PREPULL=$n; n=$((n+1))
for s in 1 2 3; do k=yes; [ $s = 3 ] && k=no
  job "p2-E256k-s$s" p2-engine $PROBE $k "ZEND_BIN=\\\$HOME/candle-bench/agent-bench/cloud/bin/zend-win262144 ${ZE}" "--backend zend --tasks-file ../stuck15.txt --workers 4 --seed $s --label p2-E256k-s$s"; done
for arm in B C; do for s in 1 2 3; do k=yes; [ $arm = C ] && [ $s = 3 ] && k=no
  pol="--policy recency"; [ $arm = C ] && pol="--policy relevance --embed-model BAAI/bge-small-en-v1.5"
  job "p2-${arm}hard-s$s" p2-hardcap $PROBE $k "" "--backend vllm --max-model-len 65536 $pol --budget-tokens 32768 --clip-recent --tasks-file ../stuck15.txt --workers 4 --seed $s --label p2-${arm}hard-s$s"; done; done
for arm in B C; do k=yes; [ $arm = C ] && k=no
  pol="--policy recency"; [ $arm = C ] && pol="--policy relevance --embed-model BAAI/bge-small-en-v1.5"
  job "p2-${arm}150" p2-verified $PREPULL $k "" "--backend vllm --max-model-len 65536 $pol --budget-tokens 32768 --clip-recent --dataset verified --tasks-file ../verified150.txt --workers 8 --seed 1 --label p2-${arm}150"; done
echo "-- $(ls "$OUT" | wc -l) jobs in $OUT; drop them into agent-bench/queue/ in order (one device_commit_files call each so mtimes stay ordered)"
