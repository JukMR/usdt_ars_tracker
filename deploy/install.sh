#!/usr/bin/env bash
# Install/update the crypto tracker on this machine as a systemd *user* service.
#
# Usage:
#   bash deploy/install.sh                 # host 0.0.0.0, port 8091
#   PORT=8092 bash deploy/install.sh
#   HOST=127.0.0.1 bash deploy/install.sh
#
# Idempotent: safe to re-run after pulling/syncing new code.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8091}"
HOST="${HOST:-0.0.0.0}"
UNIT_NAME="crypto-tracker.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

cd "$APP_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed. Install it with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "==> Installing dependencies in $APP_DIR"
uv sync --locked --quiet

if [[ ! -f config.toml ]]; then
  echo "==> Creating config.toml (host=$HOST port=$PORT)"
  sed -e "s|__HOST__|$HOST|g" -e "s|__PORT__|$PORT|g" \
    deploy/config.toml.template > config.toml
else
  echo "==> Keeping existing config.toml"
fi

mkdir -p data logs "$UNIT_DIR"
echo "==> Installing $UNIT_NAME"
install -m 644 deploy/crypto-tracker.service "$UNIT_DIR/$UNIT_NAME"

if ! loginctl show-user "$USER" --property=Linger 2>/dev/null | grep -q "Linger=yes"; then
  echo "==> Enabling linger so the service runs without an active login"
  loginctl enable-linger "$USER" || echo "warning: could not enable linger; run 'sudo loginctl enable-linger $USER'"
fi

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"
systemctl --user restart "$UNIT_NAME"

echo "==> Waiting for the dashboard on http://127.0.0.1:$PORT/health"
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -z "$LAN_IP" ]]; then
      LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
    fi
    echo "==> OK: $(systemctl --user is-active "$UNIT_NAME")"
    echo "    http://${LAN_IP:-127.0.0.1}:$PORT/  (LAN)"
    exit 0
  fi
  sleep 1
done

echo "error: the service did not become healthy; recent logs:" >&2
journalctl --user -u "$UNIT_NAME" -n 40 --no-pager >&2 || true
exit 1
