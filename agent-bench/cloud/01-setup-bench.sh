#!/usr/bin/env bash
# Run as the normal user after 00-provision.sh:  bash 01-setup-bench.sh
#
# Phase 1 (T1/T2/T3) is ZEND-ONLY, so the critical path is just the agent venv (+ Docker for
# scoring). vLLM, llama.cpp and the comparator model downloads are set up too but are optional for
# phase 1 - set COMPARATORS=0 to skip them. zend fetches its own model on first launch (HF_HOME),
# so no zend model is downloaded here. De-WSL'd from agent-bench/setup-bench.sh.
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
step() { echo; echo "== $*"; }

step "Agent venv (~/venvs/agent): mini-swe-agent + swebench harness  [REQUIRED]"
uv venv -q --python 3.12 ~/venvs/agent
VIRTUAL_ENV=~/venvs/agent uv pip install -q mini-swe-agent swebench datasets litellm pyyaml
~/venvs/agent/bin/python -c "import importlib.metadata as m; print('mini-swe-agent', m.version('mini-swe-agent'), '| swebench', m.version('swebench'))"

step "SWE-bench Lite dataset + one eval image  [needed for EVAL=1 scoring; harmless otherwise]"
~/venvs/agent/bin/python - <<'PY'
from datasets import load_dataset
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
print(len(ds), "Lite test instances; first:", ds[0]["instance_id"])
PY
docker run --rm hello-world >/dev/null 2>&1 && echo "docker ok" || echo "docker not usable yet (log out/in after 00-provision for the docker group) - only needed for EVAL=1"
docker pull -q docker.io/swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest 2>/dev/null && echo "eval image pull ok" || echo "eval image pull skipped (fine unless scoring)"

if [ "${COMPARATORS:-1}" = "0" ]; then
  echo; echo "SETUP OK (zend-only; comparators skipped)"; df -h / | tail -1; exit 0
fi

step "vLLM venv (~/venvs/vllm)  [comparator, optional for phase 1]"
uv venv -q --python 3.12 ~/venvs/vllm
VIRTUAL_ENV=~/venvs/vllm uv pip install -q vllm \
  && ~/venvs/vllm/bin/python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__, '| cuda', torch.cuda.is_available())" \
  || echo "vLLM install failed - skip; not needed for phase 1 (zend-only)"

step "llama.cpp (CUDA build) at ~/llama.cpp  [comparator, optional]"
if [ ! -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
  [ -d ~/llama.cpp ] || git clone -q https://github.com/ggml-org/llama.cpp ~/llama.cpp
  cmake -S ~/llama.cpp -B ~/llama.cpp/build -DGGML_CUDA=ON -DLLAMA_CURL=OFF >/dev/null 2>&1 \
    && cmake --build ~/llama.cpp/build --config Release -j --target llama-server >/dev/null 2>&1 \
    || echo "llama.cpp build failed - skip; not needed for phase 1"
fi

step "Comparator models  [optional; needed only to re-baseline vLLM/llama on 96 GB]"
mkdir -p ~/models
~/venvs/vllm/bin/hf download cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit >/dev/null 2>&1 && echo "vllm awq ok" || echo "awq download skipped"
# llama.cpp GGUF (same checkpoint). CONFIRM the repo id against the one thor used before relying on it:
~/venvs/agent/bin/python - <<'PY' 2>/dev/null || echo "gguf download skipped - set the correct repo id in 01-setup-bench.sh if you need the llama comparator"
from huggingface_hub import hf_hub_download
import os
p = hf_hub_download("unsloth/Qwen3.6-35B-A3B-GGUF", "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
                    local_dir=os.path.expanduser("~/models"))
print("gguf at", p)
PY

df -h / | tail -1
echo "SETUP OK"
