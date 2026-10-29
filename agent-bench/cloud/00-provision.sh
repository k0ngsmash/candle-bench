#!/usr/bin/env bash
# Phase-1 provisioning for a fresh Ubuntu 24.04 cloud box with an RTX PRO 6000 (96 GB).
# Run once, with sudo:  sudo bash 00-provision.sh
# Installs Docker + NVIDIA container toolkit (for SWE-bench scoring), build deps, the CUDA
# toolkit if absent, and Rust for the invoking user. De-WSL'd from agent-bench/provision-ubuntu.sh.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
REAL_USER="${SUDO_USER:-$USER}"

echo "== GPU check"
nvidia-smi --query-gpu=name,driver_version,memory.total,pcie.link.gen.current,pcie.link.width.current --format=csv \
  || { echo "!! nvidia-smi not working - fix the driver before continuing"; exit 1; }

echo "== base packages"
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg git jq python3 python3-venv build-essential cmake pkg-config libssl-dev

echo "== CUDA toolkit (nvcc) if missing"
if ! command -v nvcc >/dev/null && [ ! -x /usr/local/cuda/bin/nvcc ]; then
  echo "   nvcc not found. Most GPU images ship it; if yours does not, install the matching"
  echo "   cuda-toolkit for this driver, e.g.:  apt-get install -y cuda-toolkit-13-0"
  echo "   (left manual - the exact package depends on the image's driver version)"
fi

echo "== Docker Engine"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin

echo "== NVIDIA container toolkit (GPU inside SWE-bench eval containers)"
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -q
apt-get install -y -q nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker || true
usermod -aG docker "$REAL_USER" || true

echo "== Rust (rustup) for $REAL_USER"
sudo -u "$REAL_USER" bash -lc 'command -v cargo >/dev/null || (curl -LsSf https://sh.rustup.rs | sh -s -- -y)'

echo "== uv (Python) for $REAL_USER"
sudo -u "$REAL_USER" bash -lc 'command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh)'

df -h /
echo "PROVISION OK - log out/in (or 'newgrp docker') so the docker group applies, then run 01-setup-bench.sh as $REAL_USER"
