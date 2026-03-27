# Arduino Distance Alarm (Rebuild)

Dieses Projekt wurde neu aufgebaut, damit der Datenfluss stabil ist:

Arduino (Serial) -> Python Server -> SSE -> Browser Dashboard

## Warum diese Version robuster ist

- Kein Socket.IO und keine Frontend-CDN-Abhaengigkeit
- Live-Stream via **SSE** (`/events`) mit Auto-Reconnect im Browser
- Strikter Serial-Parser mit Validierung und Toleranz fuer Boot-Noise
- Klare Diagnose-Endpunkte (`/health`, `/state`)
- Automatischer Demo-Fallback, wenn kein Arduino verfuegbar ist
- Verbesserte UI mit Health-Panel, Trend-KPIs, Pause/Reconnect und CSV-Export

## Start

```bash
cd ~/Projects/adruino-alarm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Dashboard: [http://localhost:5050](http://localhost:5050)

## Einfacher Start (empfohlen)

Ab jetzt brauchst du normalerweise nur noch diese Kurzbefehle:

```bash
cd ~/Projects/adruino-alarm
./start.sh
```

Was `./start.sh` automatisch macht:

- erkennt den Arduino-Port automatisch
- startet den Server auf Port `5050`
- beendet eine alte `server.py`-Instanz auf dem gleichen Port automatisch

Weitere kurze Varianten:

```bash
./start.sh demo            # Demo-Modus
HTTP_PORT=5060 ./start.sh  # anderer HTTP-Port
./stop.sh                  # Server stoppen
```

## Wichtige Optionen

```bash
python server.py --demo
python server.py --list-ports
python server.py --serial-port /dev/cu.usbmodemXXXX --baud 9600
python server.py --http-port 5050
```

`ARDUINO_PORT` wird ebenfalls unterstuetzt:

```bash
export ARDUINO_PORT=/dev/cu.usbmodemXXXX
python server.py
```

## API/Debug

- `GET /health` -> Health, Mode, letzter Fehler, Client-Anzahl
- `GET /state` -> Letzter Messwert + History
- `GET /events` -> SSE Live-Stream

## Arduino Sketch

Datei: `skechAdruinoAlarm/skechAdruinoAlarm.ino`

Das Serial-Format ist bewusst strikt:

```text
distance,state
```

Beispiel:

```text
23,0
11,1
4,2
```

## Troubleshooting

- Kein Live-Update im Browser:
  - `http://localhost:5050/health` aufrufen und `mode`, `last_error` pruefen
  - `http://localhost:5050/state` pruefen, ob Messwerte ankommen
- Arduino wird nicht gefunden:
  - `python server.py --list-ports`
  - dann mit `--serial-port` starten
- Nur Demo-Daten sichtbar:
  - Port/Baudrate kontrollieren (normalerweise 9600)
  - Sketch neu flashen und USB-Verbindung pruefen
