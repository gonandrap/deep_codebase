#!/bin/bash
# DeepWiki startup script for auto_heycrypto
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use Docker Desktop socket (user-level, no sudo needed)
export DOCKER_HOST=unix:///home/gonzalo/.docker/desktop/docker.sock

echo "=== DeepWiki for auto_heycrypto ==="
echo ""

# Check .env exists
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found in $SCRIPT_DIR"
  exit 1
fi

# Start Docker Desktop user service if not running
if [ ! -S "$HOME/.docker/desktop/docker.sock" ]; then
  echo "[0/3] Starting Docker Desktop..."
  systemctl --user start docker-desktop
  echo "      Waiting for Docker Desktop to initialize..."
  sleep 10
fi

# Verify docker connectivity
if ! docker ps > /dev/null 2>&1; then
  echo "ERROR: Cannot connect to Docker. Is Docker Desktop running?"
  echo "Run: systemctl --user start docker-desktop"
  exit 1
fi

STATUS=$(docker compose ps --format json 2>/dev/null | python3 -c "import sys,json; data=sys.stdin.read(); items=[json.loads(l) for l in data.strip().split('\n') if l]; running=[x for x in items if x.get('State')=='running']; print('running' if running else 'stopped')" 2>/dev/null || echo "stopped")

if [ "$STATUS" = "running" ]; then
  echo "DeepWiki is already running!"
else
  echo "[1/2] Starting DeepWiki..."
  docker compose up -d
  echo "      Waiting for services to be ready..."
  sleep 12
fi

echo ""
echo "=== DeepWiki is running! ==="
echo ""
echo "  Frontend:  http://localhost:3000"
echo "  API:       http://localhost:8001/health"
echo ""
echo "To generate wiki for auto_heycrypto:"
echo "  1. Open http://localhost:3000"
echo "  2. Enter your GitHub repo URL"
echo "  3. Select 'OpenAI' as the model provider"
echo "  4. The .devin/wiki.json in the repo is auto-detected"
echo ""
echo "To stop:    docker compose --project-directory $SCRIPT_DIR down"
echo "To logs:    DOCKER_HOST=$DOCKER_HOST docker compose --project-directory $SCRIPT_DIR logs -f"
