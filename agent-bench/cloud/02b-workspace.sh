#!/usr/bin/env bash
# Create the minimal standalone workspace zend needs (passthrough only). Run once.
#   bash 02b-workspace.sh        -> ~/zend-ws  (override with WS=...)
set -euo pipefail
WS="${WS:-$HOME/zend-ws}"
mkdir -p "$WS/scratch" "$WS/jobs-agent"
printf 'repos:\n  - name: scratch\n' > "$WS/workspace.yaml"
if [ ! -d "$WS/scratch/.git" ]; then
  git -C "$WS/scratch" init -q -b main
  echo 'Placeholder repository: zend requires one; the benchmark uses passthrough only.' > "$WS/scratch/README.md"
  git -C "$WS/scratch" add README.md
  git -C "$WS/scratch" -c user.name=bench -c user.email=bench@localhost commit -q -m placeholder
fi
cat > "$WS/agent.yaml" <<YAML
jobs_dir: $WS/jobs-agent
slots: 1
checkouts:
  - name: scratch
    dir: $WS/scratch
    push: false
YAML
echo "workspace ready at $WS"
