# How it works

## Starting the CLI

```bash
python drone_cli.py                                        # SITL + QGC proxy on 127.0.0.1:14550
python drone_cli.py --gcs-port 0                          # SITL, proxy disabled
python drone_cli.py --backend pixhawk                     # Pixhawk via tcp:127.0.0.1:5760
python drone_cli.py --backend pixhawk --connect /dev/ttyUSB0
python drone_cli.py --interval 1.0                        # refresh telemetry every 1 s
```

On launch the CLI:
1. Applies per-backend connection defaults when `--connect` is omitted.
2. Instantiates the selected backend controller.
3. Calls `controller.connect()` — blocks until the vehicle (or SITL) is ready.
4. Prints the connection string, then enters the curses screen.

For QGC integration details see [proxy.md](proxy.md).

---

## The curses screen

Refreshes every `--interval` seconds (default 2 s) and immediately after every keystroke.

| Section | Content |
|---|---|
| Vehicle snapshot | Mode, system status, armable, armed, altitude, GPS location, attitude (roll/pitch/yaw), velocity, battery |
| Connection details | Vehicle connection string; GCS proxy target when active |
| Last command | Result of the most recently submitted command |
| Command line | Fixed hint + input prompt (`> `) |

Typing builds a command in the buffer. Backspace removes the last character. Enter submits.

---

## Commands

### `takeoff <altitude>`

Arms and climbs to the requested altitude in metres AGL.

1. Polls until the autopilot reports `is_armable` (up to 60 s).
2. Sets mode to GUIDED; retries every second until confirmed.
3. Sets `vehicle.armed = True`; retries until confirmed.
4. Calls `simple_takeoff(altitude)`.

The CLI does not block during the climb — telemetry keeps refreshing while the vehicle rises.

```
> takeoff 10
```

---

### `land`

Switches to LAND mode. The autopilot descends and disarms automatically.

```
> land
```

---

### `altitude <metres>`

Changes target altitude while airborne. Fire-and-forget — the autopilot climbs or descends in the background.

Requires the vehicle to be armed. Switches to GUIDED mode first if needed.

```
> altitude 20
```

---

### `forward <metres>` / `back <metres>`

Moves the drone relative to the direction it is currently facing.

Heading is read from `vehicle.attitude.yaw` (radians, 0 = North, CW positive). The distance is projected onto lat/lon offsets:

```
d_lat = distance × cos(yaw) / 111 320
d_lon = distance × sin(yaw) / (111 320 × cos(lat))
```

`back` negates both offsets. Current altitude is preserved. Fire-and-forget.

```
> forward 5
> back 3
```

---

### `left <degrees>` / `right <degrees>`

Rotates the drone in place relative to its current heading using `MAV_CMD_CONDITION_YAW` with the relative-offset flag.

`left` = counter-clockwise, `right` = clockwise.

```
> right 90
> left 45
```

---

### `quit` / `exit`

Closes the curses UI cleanly. The `finally` block calls `controller.close()`, which:
- Removes the GCS proxy listener and closes the UDP socket (SITL only).
- Closes the DroneKit vehicle connection.
- Stops the SITL process (SITL only).

---

## Backend selection

| `--backend` | Connects to | `--connect` default |
|---|---|---|
| `sitl` | dronekit-sitl subprocess (ArduCopter 3.3) | assigned by SITL |
| `pixhawk` | Physical Pixhawk over serial or TCP/UDP | `tcp:127.0.0.1:5760` |
| `mavlink` | Future pymavlink backend (not yet implemented) | `tcp:127.0.0.1:5760` |

All backends expose the same CLI commands. The `mavlink` backend raises "not yet implemented" on every call, which is caught and displayed in the status line.

---

## Dependencies (DroneKit backends)

Requires **Python 3.7** due to DroneKit compatibility. Defined in `dronekit_version/requirements-3.7.17.txt`.

| Package | Version | Purpose |
|---|---|---|
| dronekit | 2.9.2 | High-level vehicle API |
| dronekit-sitl | 3.3.0 | Bundles and launches ArduPilot SITL |
| pymavlink | 2.4.8 | Raw MAVLink message construction (yaw rotation) |
| pyserial | 3.5 | Serial port access for Pixhawk USB connections |
| Cython, future, lxml, monotonic, psutil, six | various | DroneKit transitive dependencies |
