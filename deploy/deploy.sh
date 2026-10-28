#!/usr/bin/env bash
# Pull the latest code, rebuild and restart the stack. Run on the server.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only
docker compose up -d --build
# Remove the previous image layers so the disk does not fill up over many deploys.
docker image prune -f
docker compose ps
