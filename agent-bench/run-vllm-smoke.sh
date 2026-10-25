#!/usr/bin/env bash
# vLLM attempt on the 2 smoke tasks: pinned memory under WSL2, plus the Linux CUDA toolkit and
# FlashInfer's prebuilt kernels so its sampler does not have to compile without a compiler.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/harness"
LINUX_PATH="$(echo "$PATH" | tr ':' '\n' | grep -v '^/mnt/' | paste -sd:)"
if [ ! -x /usr/local/cuda/bin/nvcc ]; then
  echo "== CUDA toolkit 13.0 for WSL-Ubuntu (compiler and headers only; the driver comes from Windows)"
  cd /tmp && wget -q https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb \
    && sudo dpkg -i cuda-keyring_1.1-1_all.deb > /dev/null && sudo apt-get update -q > /dev/null \
    && sudo apt-get install -y -q cuda-toolkit-13-0 > /dev/null && echo "installed"
  cd - > /dev/null
fi
/usr/local/cuda/bin/nvcc --version | tail -2
echo "== FlashInfer prebuilt kernels"
env PATH="/usr/local/cuda/bin:$LINUX_PATH" CUDA_HOME=/usr/local/cuda ~/venvs/vllm/bin/vllm download-kernels 2>&1 | tail -3
~/venvs/agent/bin/python run_bench.py --backend vllm --tasks 2 --workers 1 --label smoke-pin --offloads 6,8,10
echo "VLLM SMOKE DONE"
