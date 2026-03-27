"""
Arduino Distance Alarm - Rebuilt backend (Flask + SSE)

Data flow:
Arduino Serial -> Parser/Validator -> Shared State -> SSE -> Browser Dashboard

Run:
  python server.py
  python server.py --demo
  python server.py --list-ports
  python server.py --serial-port /dev/cu.usbmodemXXXX
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import signal
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from queue import Empty, Full, Queue
from typing import Optional

from flask import Flask, Response, jsonify, render_template, stream_with_context

try:
    import serial
    import serial.tools.list_ports
except Exception:  # pragma: no cover - handled at runtime
    serial = None


# --------------------------
# Config
# --------------------------
HISTORY_LIMIT = 300
SSE_CLIENT_QUEUE = 100
READ_TIMEOUT_SECONDS = 1.0
RECONNECT_DELAY_SECONDS = 2.0
DEMO_INTERVAL_SECONDS = 0.4
WARN_DISTANCE_CM = 15
ALARM_DISTANCE_CM = 5


@dataclass
class Measurement:
    distance: int
    state: int
    timestamp_iso: str
    source: str  # "serial" or "demo"


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latest: Optional[Measurement] = None
        self.history: deque[Measurement] = deque(maxlen=HISTORY_LIMIT)
        self.clients: list[Queue[str]] = []

        self.mode = "starting"  # starting|serial|demo
        self.serial_connected = False
        self.serial_port: Optional[str] = None
        self.last_error: Optional[str] = None
        self.started_at = time.time()

    def publish(self, measurement: Measurement) -> None:
        payload = json.dumps({"type": "update", "data": asdict(measurement)}, ensure_ascii=True)
        with self.lock:
            self.latest = measurement
            self.history.append(measurement)
            clients = list(self.clients)

        for q in clients:
            try:
                q.put_nowait(payload)
            except Full:
                # Drop if client can't keep up; UI will reconnect/fetch state.
                pass

    def register_client(self) -> Queue[str]:
        q: Queue[str] = Queue(maxsize=SSE_CLIENT_QUEUE)
        with self.lock:
            self.clients.append(q)
            latest = self.latest
        if latest:
            snapshot = json.dumps({"type": "snapshot", "data": asdict(latest)}, ensure_ascii=True)
            try:
                q.put_nowait(snapshot)
            except Full:
                pass
        return q

    def unregister_client(self, q: Queue[str]) -> None:
        with self.lock:
            self.clients = [client for client in self.clients if client is not q]

    def snapshot(self) -> dict:
        with self.lock:
            latest = asdict(self.latest) if self.latest else None
            history_items = list(self.history)
            history = [asdict(item) for item in history_items[-50:]]
            client_count = len(self.clients)
            serial_connected = self.serial_connected
            serial_port = self.serial_port
            mode = self.mode
            last_error = self.last_error

        stats = {
            "samples": 0,
            "min_distance": None,
            "max_distance": None,
            "avg_distance": None,
            "avg_distance_last10": None,
        }
        if history_items:
            distances = [item.distance for item in history_items]
            last10 = distances[-10:]
            stats = {
                "samples": len(distances),
                "min_distance": min(distances),
                "max_distance": max(distances),
                "avg_distance": round(sum(distances) / len(distances), 1),
                "avg_distance_last10": round(sum(last10) / len(last10), 1),
            }

        return {
            "latest": latest,
            "history": history,
            "mode": mode,
            "serial_connected": serial_connected,
            "serial_port": serial_port,
            "last_error": last_error,
            "client_count": client_count,
            "stats": stats,
            "thresholds": {
                "warn_distance_cm": WARN_DISTANCE_CM,
                "alarm_distance_cm": ALARM_DISTANCE_CM,
            },
            "server_time_iso": datetime.now().isoformat(timespec="seconds"),
        }


def state_from_distance(distance: int) -> int:
    if distance <= ALARM_DISTANCE_CM:
        return 2
    if distance <= WARN_DISTANCE_CM:
        return 1
    return 0


def parse_serial_line(line: str) -> Optional[tuple[int, int]]:
    """
    Accepts formats:
    - "<distance>,<state>" (preferred)
    - "<distance>;<state>"
    - "<distance>" (state derived from threshold)
    """
    cleaned = line.strip()
    if not cleaned:
        return None

    sep = ","
    normalized = cleaned.replace(";", ",")

    if sep in normalized:
        left, right = normalized.split(sep, maxsplit=1)
        try:
            distance = int(left.strip())
        except ValueError:
            nums = re.findall(r"-?\d+", left)
            if not nums:
                return None
            distance = int(nums[0])

        try:
            state = int(right.strip())
        except ValueError:
            nums = re.findall(r"-?\d+", right)
            state = int(nums[0]) if nums else state_from_distance(distance)
    else:
        try:
            distance = int(normalized)
            state = state_from_distance(distance)
        except ValueError:
            nums = re.findall(r"-?\d+", normalized)
            if not nums:
                return None
            distance = int(nums[0])
            state = int(nums[1]) if len(nums) >= 2 else state_from_distance(distance)

    if distance < 0 or distance > 400:
        return None

    if state not in (0, 1, 2):
        state = state_from_distance(distance)

    return distance, state


def list_ports() -> list[str]:
    if serial is None:
        return []
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]


def find_serial_port(explicit_port: Optional[str]) -> Optional[str]:
    if explicit_port:
        return explicit_port

    env_port = os.getenv("ARDUINO_PORT")
    if env_port:
        return env_port

    if serial is None:
        return None

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    preferred = []
    fallback = []
    for p in ports:
        dev = (p.device or "").lower()
        desc = (p.description or "").lower()
        if "arduino" in desc or "usbmodem" in dev or "usbserial" in dev:
            preferred.append(p.device)
        else:
            fallback.append(p.device)

    if preferred:
        return preferred[0]
    return fallback[0] if fallback else None


class SensorWorker(threading.Thread):
    def __init__(self, app_state: SharedState, explicit_port: Optional[str], baud: int, force_demo: bool):
        super().__init__(daemon=True)
        self.app_state = app_state
        self.explicit_port = explicit_port
        self.baud = baud
        self.force_demo = force_demo
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        if self.force_demo:
            self.run_demo_loop("--demo aktiv")
            return

        while not self.stop_event.is_set():
            if serial is None:
                self.run_demo_loop("pyserial fehlt")
                return

            port = find_serial_port(self.explicit_port)
            if not port:
                self.run_demo_loop("kein serieller Port gefunden")
                return

            try:
                with serial.Serial(port, self.baud, timeout=READ_TIMEOUT_SECONDS) as ser_conn:
                    # Board reset wait (common on Arduino over USB)
                    time.sleep(2.0)

                    with self.app_state.lock:
                        self.app_state.mode = "serial"
                        self.app_state.serial_connected = True
                        self.app_state.serial_port = port
                        self.app_state.last_error = None

                    while not self.stop_event.is_set():
                        raw = ser_conn.readline()
                        if not raw:
                            continue

                        line = raw.decode(errors="ignore").strip()
                        parsed = None
                        try:
                            parsed = parse_serial_line(line)
                        except ValueError:
                            # Ignore non-data boot/log lines from MCU
                            parsed = None

                        if parsed is None:
                            continue

                        distance, state = parsed
                        self.app_state.publish(
                            Measurement(
                                distance=distance,
                                state=state,
                                timestamp_iso=datetime.now().isoformat(timespec="seconds"),
                                source="serial",
                            )
                        )

            except Exception as exc:
                with self.app_state.lock:
                    self.app_state.serial_connected = False
                    self.app_state.last_error = f"Serialfehler auf {port}: {exc}"
                time.sleep(RECONNECT_DELAY_SECONDS)

    def run_demo_loop(self, reason: str) -> None:
        with self.app_state.lock:
            self.app_state.mode = "demo"
            self.app_state.serial_connected = False
            self.app_state.serial_port = None
            self.app_state.last_error = f"Demo aktiv: {reason}"

        current = 22
        while not self.stop_event.is_set():
            current += random.randint(-5, 5)
            current = max(3, min(60, current))
            self.app_state.publish(
                Measurement(
                    distance=current,
                    state=state_from_distance(current),
                    timestamp_iso=datetime.now().isoformat(timespec="seconds"),
                    source="demo",
                )
            )
            time.sleep(DEMO_INTERVAL_SECONDS)


def create_app() -> tuple[Flask, SharedState]:
    app = Flask(__name__)
    app_state = SharedState()

    @app.route("/")
    def index() -> str:
        return render_template("index.html")

    @app.route("/health")
    def health() -> Response:
        snap = app_state.snapshot()
        latest = snap["latest"]
        age_seconds = None
        if latest:
            ts = datetime.fromisoformat(latest["timestamp_iso"])
            age_seconds = int(max(0, (datetime.now() - ts).total_seconds()))

        return jsonify(
            {
                "status": "ok",
                "uptime_seconds": int(time.time() - app_state.started_at),
                "mode": snap["mode"],
                "serial_connected": snap["serial_connected"],
                "serial_port": snap["serial_port"],
                "last_update_age_seconds": age_seconds,
                "last_error": snap["last_error"],
                "client_count": snap["client_count"],
            }
        )

    @app.route("/state")
    def state() -> Response:
        return jsonify(app_state.snapshot())

    @app.route("/events")
    def events() -> Response:
        def stream() -> str:
            queue = app_state.register_client()
            try:
                # Immediate comment to establish stream in some proxies/browsers.
                yield ": connected\n\n"
                while True:
                    try:
                        payload = queue.get(timeout=15)
                        yield f"event: update\ndata: {payload}\n\n"
                    except Empty:
                        yield ": keepalive\n\n"
            finally:
                app_state.unregister_client(queue)

        headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
        return Response(stream_with_context(stream()), mimetype="text/event-stream", headers=headers)

    return app, app_state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Arduino Distance Alarm Server")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--http-port", type=int, default=5050, help="HTTP port (default: 5050)")
    parser.add_argument("--serial-port", help="Serial port, e.g. /dev/cu.usbmodem14101")
    parser.add_argument("--baud", type=int, default=9600, help="Serial baudrate (default: 9600)")
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit")
    parser.add_argument("--demo", action="store_true", help="Force demo mode")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    if args.list_ports:
        ports = list_ports()
        if not ports:
            print("Keine seriellen Ports gefunden.")
        else:
            for p in ports:
                print(p)
        return

    app, app_state = create_app()
    worker = SensorWorker(app_state, explicit_port=args.serial_port, baud=args.baud, force_demo=args.demo)
    worker.start()

    def shutdown_handler(*_ignored: object) -> None:
        worker.stop()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("=" * 56)
    print(f"Dashboard: http://localhost:{args.http_port}")
    print(f"Mode: {'demo' if args.demo else 'auto (serial, fallback demo)'}")
    print(f"Serial Port: {args.serial_port or os.getenv('ARDUINO_PORT') or 'auto-detect'}")
    print(f"Baudrate: {args.baud}")
    print("=" * 56)

    app.run(host=args.host, port=args.http_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
