#!/bin/bash
# Smart Reverse Corridor — Demo Launcher
# Usage: ./scripts/demo.sh [scenario]
# Default scenario: showcase

set -e
cd "$(dirname "$0")/.."
SCENARIO=${1:-showcase}

echo "🚦 Smart Reverse Corridor — Starting demo..."
echo "   Scenario: $SCENARIO"
echo ""

# Ensure .env exists
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📋 Created .env from .env.example"
fi

# Build and start core stack
echo "🐳 Building and starting core services..."
docker compose up -d --build

# Wait for controller to be healthy
echo "⏳ Waiting for controller..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Controller ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "⚠️  Controller not responding after 30s, continuing anyway..."
  fi
  sleep 1
done

# Start simulator with chosen scenario in adaptive mode
echo "🎬 Starting simulator (scenario: $SCENARIO, mode: adaptive)..."
SIM_SCENARIO=$SCENARIO SIM_MODE=adaptive docker compose --profile sim up -d --build

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎬 Demo running!"
echo ""
echo "   🖥  Dashboard:  http://localhost:5173"
echo "   🎛  API:        http://localhost:8000"
echo "   📊 Grafana:    http://localhost:3001"
echo "   🦟 MQTT WS:    ws://localhost:9001"
echo ""
echo "   Scenario: $SCENARIO | Mode: adaptive"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "To stop: ./scripts/demo-stop.sh"
