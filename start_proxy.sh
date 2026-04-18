#!/usr/bin/env bash
# Start the Cursor API proxy using CURSOR_API_KEY from .env
#
# One-time setup:
#   1. Go to cursor.com/dashboard → Cloud Agents → User API Keys
#   2. Click "Create New API Key", copy it
#   3. Add to .env:  CURSOR_API_KEY=your-key-here
#
# Then run:  bash start_proxy.sh

set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"

# Load .env
if [[ -f "$ENV_FILE" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +o allexport
else
  echo "ERROR: .env not found at $ENV_FILE"
  exit 1
fi

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  echo "ERROR: CURSOR_API_KEY not set in .env"
  echo ""
  echo "  1. Go to cursor.com/dashboard → Cloud Agents → User API Keys"
  echo "  2. Click 'Create New API Key' and copy it"
  echo "  3. Add to .env:  CURSOR_API_KEY=your-key-here"
  exit 1
fi

PORT=8765

# Kill anything on the port
if lsof -ti :"$PORT" &>/dev/null; then
  echo "Clearing port $PORT..."
  lsof -ti :"$PORT" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

echo "✓ CURSOR_API_KEY loaded"
echo "Starting Cursor proxy on http://localhost:$PORT ..."

export CURSOR_API_KEY
exec npx cursor-api-proxy
