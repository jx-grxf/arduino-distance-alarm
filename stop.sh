#!/usr/bin/env bash
set -euo pipefail

HTTP_PORT="${HTTP_PORT:-5050}"

pids="$(lsof -ti tcp:"$HTTP_PORT" -sTCP:LISTEN || true)"
if [[ -z "$pids" ]]; then
  echo "Kein Prozess auf Port $HTTP_PORT aktiv."
  exit 0
fi

while IFS= read -r pid; do
  [[ -z "$pid" ]] && continue
  cmd="$(ps -p "$pid" -o command= || true)"
  if [[ "$cmd" == *"server.py"* ]]; then
    echo "Stoppe Server PID $pid"
    kill "$pid" || true
    sleep 0.3
    if ps -p "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" || true
    fi
  else
    echo "Prozess PID $pid auf Port $HTTP_PORT ist kein server.py:"
    echo "$cmd"
  fi
done <<< "$pids"

echo "Fertig."
