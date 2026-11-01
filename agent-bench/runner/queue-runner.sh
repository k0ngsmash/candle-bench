#!/usr/bin/env bash
# candle-bench job runner. Runs only while the window started by start-runner.cmd is open; closing
# that window, logging out or rebooting ends it. Nothing restarts it automatically.
#
# Runs jobs in agent-bench/queue/, one at a time, oldest first (by mtime):
#   queue/<name>.sh  -> queue/running/, run with bash from agent-bench/
#   output           -> queue/logs/<time>_<name>.log, with the job's contents, times and exit code
#   afterwards       -> queue/done/<time>_<name>.sh, a line in queue/history.tsv and one in queue/status.md
# Only plain files directly in queue/ named [A-Za-z0-9._-]+.sh are run.
# queue/STOP pauses everything (the current job finishes first). queue/runner.alive shows it is polling.
#
# Header directives a job may carry (comment lines near the top):
#   # after: 69l, 69j        run only once each named job has exited 0. A name matches a job whose
#                            basename equals it or starts with "<name>-". A dependency that has not
#                            run yet defers this job (others may run first); one that FAILED skips
#                            this job (moved to done/ as *_SKIPPED.sh, exit "skipped" in history).
#   # group: p1-matrix       membership in a group.
#   # on-fail: pause-group   (default when a group is set) when this job exits non-zero, create
#                            queue/paused.<group>; jobs of that group are then HELD in the queue
#                            until that file is deleted. "continue" disables this.
set -uo pipefail
BENCH=${BENCH:-/mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench}
Q="$BENCH/queue"
mkdir -p "$Q/running" "$Q/done" "$Q/logs"
exec 9>"${RUNNER_LOCK:-/tmp/bench-runner.lock}"
flock -n 9 || { echo "A runner is already active in another window."; exit 0; }
export PATH="$HOME/.local/bin:$PATH"
[ -f "$Q/history.tsv" ] || printf 'job\tstart\tend\texit\n' > "$Q/history.tsv"
[ -f "$Q/status.md" ] || printf '# queue status (newest last)\n\n| finished | job | exit | took | last line |\n|---|---|---|---|---|\n' > "$Q/status.md"

directive() {  # directive <file> <key>  -> value (empty if absent)
  sed -n -E "1,20s/^#[[:space:]]*$2:[[:space:]]*(.*)$/\1/p" "$1" | head -1 | tr -d '\r'
}
last_exit() {  # last_exit <depname> -> exit code of the most recent matching history row, or "" if never run
  awk -F'\t' -v d="$1" 'NR>1 { b=$1; sub(/\.sh$/,"",b); if (b==d || index(b, d"-")==1) e=$4 } END { print e }' "$Q/history.tsv"
}
record() {  # record <job> <start> <end> <exit> <took> <lastline>
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$Q/history.tsv"
  local ll; ll=$(printf '%s' "$6" | tr '|' '/' | cut -c1-140)
  printf '| %s | %s | %s | %s | %s |\n' "${3#*T}" "$1" "$4" "$5" "$ll" >> "$Q/status.md"
}

echo "Runner active $(date '+%H:%M:%S'). Watching $Q"
echo "Close this window to stop it. Create queue\\STOP to pause it. Delete queue\\paused.<group> to resume a group."
while true; do
  date -Is > "$Q/runner.alive"
  if [ -e "$Q/STOP" ]; then sleep 15; continue; fi
  picked=""; action=""
  while IFS= read -r job; do
    [ -n "$job" ] || continue
    f="$Q/$job"
    group=$(directive "$f" group)
    if [ -n "$group" ] && [ -e "$Q/paused.$group" ]; then continue; fi          # held
    deps=$(directive "$f" after | tr ',' ' ')
    state="run"
    for d in $deps; do
      e=$(last_exit "$d")
      if [ -z "$e" ]; then state="defer"; break; fi
      if [ "$e" != "0" ]; then state="skip:$d:$e"; break; fi
    done
    [ "$state" = "defer" ] && continue
    picked="$job"; action="$state"; break
  done < <(find "$Q" -maxdepth 1 -type f -regextype posix-extended -regex '.*/[A-Za-z0-9._-]+\.sh' -printf '%T@ %f\n' 2>/dev/null | sort -n | cut -d' ' -f2-)
  if [ -z "$picked" ]; then sleep 10; continue; fi
  stamp=$(date +%Y%m%d-%H%M%S)
  now=$(date -Is)
  if [[ "$action" == skip:* ]]; then
    IFS=: read -r _ dep dexit <<<"$action"
    echo "[$(date '+%H:%M:%S')] skipping $picked  (dependency $dep exited $dexit)"
    mv "$Q/$picked" "$Q/done/${stamp}_${picked%.sh}_SKIPPED.sh"
    record "$picked" "$now" "$now" "skipped" "-" "dependency $dep exited $dexit"
    continue
  fi
  mv "$Q/$picked" "$Q/running/$picked" || { sleep 10; continue; }
  log="$Q/logs/${stamp}_${picked%.sh}.log"
  start=$(date -Is); t0=$(date +%s)
  echo "[$(date '+%H:%M:%S')] running $picked  (log: queue/logs/${stamp}_${picked%.sh}.log)"
  { echo "== job $picked  started $start"; echo "== contents:"; sed 's/^/   | /' "$Q/running/$picked"; echo "== output:"; } > "$log"
  (cd "$BENCH" && bash -l "$Q/running/$picked") >> "$log" 2>&1
  rc=$?
  end=$(date -Is); took=$(( $(date +%s) - t0 ))
  echo "== exit $rc  finished $end" >> "$log"
  mv "$Q/running/$picked" "$Q/done/${stamp}_$picked"
  lastline=$(grep -v '^== exit' "$log" | grep -v '^\s*$' | tail -1)
  record "$picked" "$start" "$end" "$rc" "$(printf '%dm%02ds' $((took/60)) $((took%60)))" "$lastline"
  echo "[$(date '+%H:%M:%S')] finished $picked  exit $rc  ($((took/60))m)"
  group=$(directive "$Q/done/${stamp}_$picked" group)
  onfail=$(directive "$Q/done/${stamp}_$picked" on-fail)
  if [ "$rc" != "0" ] && [ -n "$group" ] && [ "${onfail:-pause-group}" = "pause-group" ]; then
    date -Is > "$Q/paused.$group"
    echo "[$(date '+%H:%M:%S')] group '$group' PAUSED after $picked failed - delete queue/paused.$group to resume"
    printf '| %s | (group %s) | paused | - | %s failed; delete queue/paused.%s to resume |\n' "${end#*T}" "$group" "$picked" "$group" >> "$Q/status.md"
  fi
done
