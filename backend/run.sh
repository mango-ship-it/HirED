#!/usr/bin/env bash
#
# Run the HirED backend + a public tunnel in ONE terminal, with hot-reload so your
# backend updates auto-apply WITHOUT restarting — the tunnel URL stays stable.
#
#   ./run.sh                                          # cloudflared (no signup)
#   NGROK_DOMAIN=your-name.ngrok-free.app ./run.sh    # ngrok static domain (permanent URL)
#
# Ctrl+C stops both. After `git pull`ing new backend code, uvicorn --reload picks it
# up automatically — no restart, same URL, frontend just re-calls the endpoint.
#
set -euo pipefail
cd "$(dirname "$0")"

# Free port 8000 if something's already on it (avoids "address already in use").
if lsof -ti :8000 >/dev/null 2>&1; then
  echo "Port 8000 busy — stopping the old backend first..."
  lsof -ti :8000 | xargs kill 2>/dev/null || true
  sleep 1
fi

# Backend with hot reload (saved/pulled code changes apply automatically).
PYTHONPATH=. .venv/bin/uvicorn app.main:app --port 8000 --reload &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT INT TERM

sleep 2  # let uvicorn bind before the tunnel attaches

if [ -n "${NGROK_DOMAIN:-}" ]; then
  echo ">> Tunnel: ngrok static domain  https://$NGROK_DOMAIN  (permanent)"
  ngrok http 8000 --url="https://$NGROK_DOMAIN"
else
  echo ">> Tunnel: cloudflared quick tunnel (stays stable while this runs)."
  echo ">> For a permanent URL, claim an ngrok domain and run: NGROK_DOMAIN=<domain> ./run.sh"
  cloudflared tunnel --url http://localhost:8000
fi
