#!/usr/bin/env bash
# Runs as root inside Ubuntu-24.04 under WSL2. Installs Docker Engine (no Docker Desktop), the
# NVIDIA container toolkit, uv for Python, and creates the 'bench' user. Idempotent.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
echo "== base packages"
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg git jq python3 python3-venv build-essential
echo "== Docker Engine"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin
echo "== NVIDIA container toolkit (GPU inside containers; vLLM itself runs in a venv)"
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -q
apt-get install -y -q nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
echo "== systemd + docker on boot"
grep -q '^\[boot\]' /etc/wsl.conf 2>/dev/null || printf '[boot]\nsystemd=true\n[user]\ndefault=bench\n' > /etc/wsl.conf
echo "== bench user"
id bench >/dev/null 2>&1 || useradd -m -s /bin/bash -G docker,sudo bench
echo 'bench ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/bench
echo "== uv"
sudo -u bench bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
echo "== GPU visible?"
/usr/lib/wsl/lib/nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv || echo "nvidia-smi not visible yet"
df -h /
echo "PROVISION OK"
