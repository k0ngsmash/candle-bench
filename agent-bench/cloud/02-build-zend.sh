#!/usr/bin/env bash
# Build zend natively on Linux for a given projection window. Grounded in the proven runtime-smoke
# recipe (job 29). Applies the six portability fixes + the 35B model switch (+ a window patch when
# the window is not the stock 32768) to the pinned base commit, builds, and copies the binary to
# cloud/bin/zend-win<window>.
#
#   bash 02-build-zend.sh <window_tokens>        e.g. 32768 | 65536 | 131072 | 262144
#   MODEL=flashnext bash 02-build-zend.sh 32768  build the stock Flash-Next model (for the T3 gate)
#
# Env overrides: FORK_URL (default the k0ngsmash fork), BASE (default the verified commit),
#                KIT (default: this script's repo), CANDLE (default ~/candle).
set -euo pipefail
WINDOW="${1:?usage: 02-build-zend.sh <window_tokens>}"
MODEL="${MODEL:-qwen36}"                       # qwen36 (35B bench model) | flashnext (stock)
FORK_URL="${FORK_URL:-https://github.com/k0ngsmash/candle.git}"
BASE="${BASE:-35e9a2b8}"                        # the commit the portability patches were cut+tested against
KIT="${KIT:-$(cd "$(dirname "$0")/../.." && pwd)}"   # the candle-bench checkout holding the patches
PATCHES="$KIT/agent-bench"
CANDLE="${CANDLE:-$HOME/candle}"

# CUDA env (same derivation as the smoke build)
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="$CUDA_HOME/bin:$HOME/.cargo/bin:$PATH"
source ~/.cargo/env 2>/dev/null || true
V=$(nvcc --version | sed -n 's/.*release \([0-9]*\)\.\([0-9]*\).*/\1\2/p'); export CUDARC_CUDA_VERSION="${V:0:2}0${V:2:1}0"

git config --global --add safe.directory '*' || true
[ -d "$CANDLE/.git" ] || git clone -q "$FORK_URL" "$CANDLE"
git -C "$CANDLE" fetch -q origin || true
git -C "$CANDLE" checkout -q -f "$BASE"
git -C "$CANDLE" clean -qfd

# six portability fixes (needed until the PR merges; harmless to keep pinned to BASE)
for p in case-fix halfraw-fix cfloat-fix overload-fix atomicadd-fix cstdio-fix; do
  git -C "$CANDLE" apply "$PATCHES/zend-linux-$p.patch" || { echo "portability patch $p failed"; exit 1; }
done
# model: qwen36 switches the stock Flash-Next to the 35B bench model; flashnext leaves it stock
if [ "$MODEL" = "qwen36" ]; then
  git -C "$CANDLE" apply "$PATCHES/zend-qwen36.patch" || { echo "model patch failed"; exit 1; }
fi
# window: stock schema is 32768, so only patch when asked for something wider
case "$WINDOW" in
  32768) : ;;
  65536)  git -C "$CANDLE" apply "$PATCHES/zend-window-64k.patch"  ;;
  131072) git -C "$CANDLE" apply "$PATCHES/zend-window-128k.patch" ;;
  262144) git -C "$CANDLE" apply "$PATCHES/zend-window-256k.patch" ;;
  *) echo "no window patch for $WINDOW (have 32768/65536/131072/262144)"; exit 1 ;;
esac

echo "== cargo build --release -p zend  (window=$WINDOW model=$MODEL base=$BASE)"
( cd "$CANDLE" && cargo build --release -p zend ) || { echo "build failed"; exit 1; }
mkdir -p "$(dirname "$0")/bin"
TAG="$WINDOW"; [ "$MODEL" = "flashnext" ] && TAG="flashnext"
install -m 0755 "$CANDLE/target/release/zend" "$(dirname "$0")/bin/zend-win$TAG"
echo "== built: cloud/bin/zend-win$TAG ($(du -h "$(dirname "$0")/bin/zend-win$TAG" | cut -f1))"
