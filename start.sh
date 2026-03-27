#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HTTP_PORT="${HTTP_PORT:-5050}"
BAUD="${BAUD:-9600}"
MODE="${1:-live}" # live|demo

find_python() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "$ROOT_DIR/.venv/bin/python"
  else
    echo "python3"
  fi
}

find_arduino_port() {
  local pybin
  pybin="$(find_python)"

  "$pybin" - <<'PY'
import glob

port = ""

try:
    import serial.tools.list_ports as lp
    ports = list(lp.comports())
    preferred = []
    fallback = []
    for p in ports:
        dev = (p.device or "")
        d = dev.lower()
        desc = (p.description or "").lower()
        if "arduino" in desc or "usbmodem" in d or "usbserial" in d:
            preferred.append(dev)
        else:
            fallback.append(dev)

    if preferred:
        port = preferred[0]
    elif fallback:
        port = fallback[0]
except Exception:
    pass

if not port:
    for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/ttyUSB*", "/dev/ttyACM*"):
        matches = sorted(glob.glob(pattern))
        if matches:
            port = matches[0]
            break

print(port)
PY
}

replace_old_server_on_port() {
  local pids
  pids="$(lsof -ti tcp:"$HTTP_PORT" -sTCP:LISTEN || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    local cmd
    cmd="$(ps -p "$pid" -o command= || true)"

    if [[ "$cmd" == *"server.py"* ]]; then
      echo "Stoppe alten Server auf Port $HTTP_PORT (PID $pid)"
      kill "$pid" || true
      sleep 0.3
      if ps -p "$pid" >/dev/null 2>&1; then
        kill -9 "$pid" || true
      fi
    else
      echo "Port $HTTP_PORT wird von einem anderen Prozess genutzt: PID $pid"
      echo "Command: $cmd"
      echo "Bitte Prozess zuerst manuell beenden oder HTTP_PORT setzen, z.B.: HTTP_PORT=5060 ./start.sh"
      exit 1
    fi
  done <<< "$pids"
}

main() {
  local pybin port
  pybin="$(find_python)"

  replace_old_server_on_port

  if [[ "$MODE" == "demo" ]]; then
    echo "Starte Dashboard im Demo-Modus auf Port $HTTP_PORT"
    exec "$pybin" server.py --demo --http-port "$HTTP_PORT" --baud "$BAUD"
  fi

  port="$(find_arduino_port | tr -d '[:space:]')"

  if [[ -n "$port" ]]; then
    echo "Arduino erkannt auf: $port"
    exec "$pybin" server.py --serial-port "$port" --baud "$BAUD" --http-port "$HTTP_PORT"
  fi

  echo "Kein Arduino-Port erkannt, starte mit Auto-Fallback (kann Demo werden)."
  exec "$pybin" server.py --baud "$BAUD" --http-port "$HTTP_PORT"
}

main "$@"
