#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 EC2 instance: Docker, Compose and swap.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 docker-buildx git
sudo systemctl enable --now docker
# Let the current user run docker without sudo (takes effect after logging in again).
sudo usermod -aG docker "$USER"

# 2 GB swap: building the frontend and pandas can briefly exceed a small instance's RAM.
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "Setup complete. Log out and SSH in again so the docker group applies."
