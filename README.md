# Arduino Distance Alarm

A real-time proximity alarm system built with an Arduino and a web-based live dashboard.

**Data flow:**

```
Arduino (Serial) → Python/Flask Server → SSE → Browser Dashboard
```

## Features

- **Ultrasonic distance sensing** via HC-SR04 with three alarm states (OK / WARNING / ALARM)
- **Visual & audio feedback** on the Arduino: RGB LEDs, potentiometer-controlled brightness, and a buzzer
- **16×2 I²C LCD** showing live distance and current state
- **Live browser dashboard** streamed over Server-Sent Events (SSE) with auto-reconnect — no Socket.IO or CDN dependencies
- **Demo mode** — simulates sensor data so you can run the dashboard without hardware
- **Strict serial parser** with boot-noise tolerance and automatic state derivation from thresholds
- **Diagnostic endpoints** (`/health`, `/state`) for quick debugging
- CSV export, trend KPIs, and pause/reconnect controls in the UI

## Hardware

| Component | Arduino Pin |
|---|---|
| HC-SR04 Trigger | D2 |
| HC-SR04 Echo | D3 |
| Green LED | D11 (PWM) |
| Yellow LED | D10 (PWM) |
| Red LED | D9 (PWM) |
| Buzzer | D6 |
| Potentiometer (brightness) | A0 |
| I²C LCD (16×2, addr 0x27) | SDA/SCL |

### Alarm States

| State | Condition | LED | Buzzer |
|---|---|---|---|
| `0` – OK | distance > 15 cm | Green | Off |
| `1` – Warning | 5 cm < distance ≤ 15 cm | Yellow | Off |
| `2` – Alarm | distance ≤ 5 cm | Red | 1200 Hz |

## Requirements

- Python 3.9+
- `flask >= 3.0`
- `pyserial >= 3.5`
- Arduino IDE (to flash the sketch)
- Arduino library: **LiquidCrystal_I2C**

## Quick Start

### 1 — Flash the Arduino

Open `skechAdruinoAlarm/skechAdruinoAlarm.ino` in the Arduino IDE, select your board and port, and upload.

### 2 — Set up the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3 — Start the server (recommended)

`start.sh` auto-detects the Arduino port, kills any old server instance on the same port, and launches the dashboard:

```bash
./start.sh              # live mode  (auto-detect Arduino)
./start.sh demo         # demo mode  (no hardware needed)
HTTP_PORT=5060 ./start.sh   # custom port
```

Open the dashboard: [http://localhost:5050](http://localhost:5050)

To stop the server:

```bash
./stop.sh
```

### Manual start

```bash
python server.py                                         # auto-detect port
python server.py --demo                                  # demo mode
python server.py --list-ports                            # list available serial ports
python server.py --serial-port /dev/cu.usbmodemXXXX     # explicit port
python server.py --serial-port /dev/cu.usbmodemXXXX --baud 9600 --http-port 5050
```

You can also set the port via environment variable:

```bash
export ARDUINO_PORT=/dev/cu.usbmodemXXXX
python server.py
```

## Serial Protocol

The Arduino sends one line per measurement at 9600 baud:

```
<distance_cm>,<state>
```

Examples:

```
23,0
11,1
4,2
```

The server also accepts `<distance_cm>;<state>` and bare `<distance_cm>` (state is then derived from the thresholds). Lines that cannot be parsed are silently ignored.

## API Reference

| Endpoint | Description |
|---|---|
| `GET /` | Live dashboard (HTML) |
| `GET /events` | SSE stream — emits `update` events with the latest measurement |
| `GET /state` | JSON snapshot: latest measurement, history (last 50), statistics, thresholds |
| `GET /health` | JSON: uptime, mode, serial port, last error, connected client count |

## Project Structure

```
.
├── server.py                        # Flask backend + serial reader
├── requirements.txt
├── start.sh                         # Convenience start script
├── stop.sh                          # Convenience stop script
├── templates/
│   └── index.html                   # Browser dashboard
└── skechAdruinoAlarm/
    └── skechAdruinoAlarm.ino        # Arduino sketch
```

## Troubleshooting

**No live updates in the browser**
- Check `http://localhost:5050/health` — inspect `mode` and `last_error`.
- Check `http://localhost:5050/state` — verify that measurements are arriving.

**Arduino not found**
- Run `python server.py --list-ports` to list available serial ports.
- Pass the correct port with `--serial-port`.

**Only demo data visible**
- Verify the baud rate (default: 9600) and USB connection.
- Re-flash the sketch and check that the correct board is selected in the Arduino IDE.
