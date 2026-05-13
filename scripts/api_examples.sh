#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}

echo "Health"
curl -s "$BASE/api/health" | python -m json.tool

echo "Agents"
curl -s "$BASE/api/agents" | python -m json.tool

echo "Run workflow"
curl -s -X POST "$BASE/api/workflows/1/run" \
  -H 'Content-Type: application/json' \
  -d '{"input":"Summarize a project issue: EMR job failed due to memory but completed after increasing memory. Create action items.","channel":"web"}' | python -m json.tool

echo "Send local channel message"
curl -s -X POST "$BASE/api/channel/message" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Create a concise manager update for successful end to end run","user_id":"local-user","channel":"local-messenger"}' | python -m json.tool
