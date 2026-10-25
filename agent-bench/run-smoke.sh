#!/usr/bin/env bash
# Smoke test of the whole pipeline on 2 tasks, one agent at a time: zend first, then vLLM.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/harness"
echo "== dependencies (idempotent)"
sudo apt-get install -y -q python3.12-dev ninja-build > /dev/null && echo "python headers + ninja ok"
VIRTUAL_ENV=~/venvs/agent uv pip install -q mcp && echo "mcp ok"
~/venvs/vllm/bin/python -c "import triton; print('triton target:', triton.runtime.driver.active.get_current_target())"
PY=~/venvs/agent/bin/python
$PY run_bench.py --backend zend --tasks 2 --workers 1 --label smoke
$PY run_bench.py --backend vllm --tasks 2 --workers 1 --label smoke
echo "SMOKE DONE"
