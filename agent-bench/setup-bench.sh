#!/usr/bin/env bash
# Runs as 'bench' inside Ubuntu (WSL2). Installs vLLM and the agent tooling into their own venvs,
# checks Docker can run SWE-bench images, and pre-downloads the vLLM-format 4-bit model.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
LOG_DIR="$(dirname "$0")/logs"; mkdir -p "$LOG_DIR"
step() { echo; echo "== $*"; }

step "Docker"
sudo systemctl restart docker
docker run --rm hello-world | head -3
docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu24.04 nvidia-smi --query-gpu=name,memory.total --format=csv || echo "GPU-in-container check failed (vLLM does not need it)"

step "vLLM venv (~/venvs/vllm)"
uv venv -q --python 3.12 ~/venvs/vllm
VIRTUAL_ENV=~/venvs/vllm uv pip install -q vllm
~/venvs/vllm/bin/python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__, '| cuda ok', torch.cuda.is_available(), torch.cuda.get_device_name(0))"

step "Agent venv (~/venvs/agent): mini-swe-agent + swebench harness"
uv venv -q --python 3.12 ~/venvs/agent
VIRTUAL_ENV=~/venvs/agent uv pip install -q mini-swe-agent swebench datasets
~/venvs/agent/bin/python -c "import importlib.metadata as m; print('mini-swe-agent', m.version('mini-swe-agent'), '| swebench', m.version('swebench'))"

step "SWE-bench Lite: dataset and one instance image"
~/venvs/agent/bin/python - <<'PY'
from datasets import load_dataset
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
print(len(ds), "Lite test instances; first:", ds[0]["instance_id"])
PY
docker pull -q docker.io/swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest && echo "image pull ok"

step "Download vLLM-format Qwen3.6-35B-A3B 4-bit (AWQ, ~25 GB)"
~/venvs/vllm/bin/hf download cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit > /dev/null && echo "download ok"
du -sh ~/.cache/huggingface 2>/dev/null
df -h / | tail -1
echo "SETUP OK"
