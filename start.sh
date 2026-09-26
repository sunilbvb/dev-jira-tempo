#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Load environment variables from .env if present
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

PORT="${TEMPO_PORT:-18114}"

echo "🚀 Starting Tempo Worklog Web Console..."
echo "📂 Project Root: $(pwd)"
echo "🌐 URL: http://localhost:$PORT"
echo "Press Ctrl+C to stop."
echo ""

if [ -f ".venv/bin/tempo-log" ]; then
    exec .venv/bin/tempo-log ui --port "$PORT" "$@"
else
    exec python3 -m tempo_log.cli ui --port "$PORT" "$@"
fi
