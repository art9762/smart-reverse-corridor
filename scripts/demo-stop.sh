#!/bin/bash
# Smart Reverse Corridor — Demo Stop
set -e
cd "$(dirname "$0")/.."

echo "🛑 Stopping demo..."
docker compose --profile sim --profile ml down
echo "✅ Done"
