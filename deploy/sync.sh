#!/usr/bin/env bash
# Sync this checkout to a remote host and (re)install the service there.
#
# Usage:
#   bash deploy/sync.sh                 # -> raspberry-5:/home/dietpi/crypto_tracking
#   bash deploy/sync.sh raspberry-5-tailscale
#   bash deploy/sync.sh raspberry-5 /srv/crypto_tracking
#
# The remote needs uv (https://astral.sh/uv/install.sh). Local runtime data
# (data/, logs/), secrets (.env) and the target's config.toml are preserved.
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-raspberry-5}"
REMOTE_DIR="${2:-/home/dietpi/crypto_tracking}"
PORT="${PORT:-8091}"

echo "==> Syncing $SOURCE_DIR -> $TARGET:$REMOTE_DIR"
rsync -az --delete \
  --exclude '.venv/' \
  --exclude '.mypy_cache/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '__pycache__/' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'config.toml' \
  --exclude '.env' \
  "$SOURCE_DIR/" "$TARGET:$REMOTE_DIR/"

echo "==> Installing on $TARGET"
ssh "$TARGET" "cd '$REMOTE_DIR' && PORT='$PORT' bash deploy/install.sh"
