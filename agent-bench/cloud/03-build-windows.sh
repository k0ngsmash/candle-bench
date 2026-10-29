#!/usr/bin/env bash
# Build all four window variants of the 35B binary for T1. ~30 min each (~2 h total).
set -euo pipefail
cd "$(dirname "$0")"
bash 02b-workspace.sh
for W in 32768 65536 131072 262144; do
  echo; echo "#### building window $W ####"
  bash 02-build-zend.sh "$W"
done
echo; echo "all window binaries:"; ls -la bin/
