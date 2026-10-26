#!/usr/bin/env bash
# candle-bench job runner. Runs only while the window started by start-runner.cmd is open; closing
# that window, logging out or rebooting ends it. Nothing restarts it automatically.
#
# Runs each job in agent-bench/queue/, one at a time, oldest first:
#   queue/<name>.sh  -> queue/running/, run with bash from agent-bench/
#   output           -> queue/logs/<time>_<name>.log, with the job's contents, times and exit code
#   afterwards       -> queue/done/<time>_<name>.sh, and a line in queue/history.tsv
# Only plain files directly in queue/ named [A-Za-z0-9._-]+.sh are run.
# queue/STOP pauses it (the current job finishes first). queue/runner.alive shows it is polling.
set -uo pipefail
BENCH=/mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench
Q="$BENCH/queue"
mkdir -p "$Q/running" "$Q/done" "$Q/logs"
exec 9>/tmp/bench-runner.lock
flock -n 9 || { echo "A runner is already active in another window."; exit 0; }
export PATH="$HOME/.local/bin:$PATH"
[ -f "$Q/history.tsv" ] || printf 'job\tstart\tend\texit\n' > "$Q/history.tsv"
echo "Runner active $(date '+%H:%M:%S'). Watching $Q"
echo "Close this window to stop it. Create queue\\STOP to pause it."
while true; do
  date -Is > "$Q/runner.alive"
  if [ -e "$Q/STOP" ]; then sleep 15; continue; fi
  job=$(find "$Q" -maxdepth 1 -type f -regextype posix-extended -regex '.*/[A-Za-z0-9._-]+\.sh' -printf '%T@ %f\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)
  if [ -z "$job" ]; then sleep 10; continue; fi
  stamp=$(date +%Y%m%d-%H%M%S)
  mv "$Q/$job" "$Q/running/$job" || { sleep 10; continue; }
  log="$Q/logs/${stamp}_${job%.sh}.log"
  start=$(date -Is)
  echo "[$(date '+%H:%M:%S')] running $job  (log: queue/logs/${stamp}_${job%.sh}.log)"
  { echo "== job $job  started $start"; echo "== contents:"; sed 's/^/   | /' "$Q/running/$job"; echo "== output:"; } > "$log"
  (cd "$BENCH" && bash -l "$Q/running/$job") >> "$log" 2>&1
  rc=$?
  end=$(date -Is)
  echo "== exit $rc  finished $end" >> "$log"
  mv "$Q/running/$job" "$Q/done/${stamp}_$job"
  printf '%s\t%s\t%s\t%s\n' "$job" "$start" "$end" "$rc" >> "$Q/history.tsv"
  echo "[$(date '+%H:%M:%S')] finished $job  exit $rc"
done
