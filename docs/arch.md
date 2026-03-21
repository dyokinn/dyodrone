# Architecture

## Overview

Three layers: an abstract controller interface, concrete backend implementations, and a terminal CLI that depends only on the abstract interface.

```
drone_controller.py               ← DroneController  (ABC)
│
├── dronekit_version/
│   ├── dronekit_controller.py    ← _DroneKitBase     (shared flight logic)
│   ├── dronekit_sitl_controller.py  ← DronekitSITLController
│   ├── dronekit_pixhawk_controller.py ← DronekitPixhawkController
│   └── gcs_proxy.py              ← GCSProxy          (UDP forwarder)
│
├── dyopilot_version/
│   └── dyopilot.py               ← PyMAVLinkController  (stub)
│
└── drone_cli.py                  ← curses CLI        (backend-agnostic)
```

---

## Abstract base — `DroneController`

`drone_controller.py` defines the only contract the CLI ever touches. Every flight operation is `@abstractmethod`. There is no backend-specific state here.

Two concrete helpers are provided so subclasses don't have to override them unless they have extra information to surface:

- `__enter__` / `__exit__` — context manager that calls `connect()` / `close()`.
- `connection_details() -> List[str]` — returns a list of human-readable connection lines for the CLI screen. Default implementation reads `active_connection`. Subclasses append extra lines (e.g. GCS proxy host/port).

---

## DroneKit shared logic — `_DroneKitBase`

`dronekit_version/dronekit_controller.py` implements all flight logic on top of DroneKit. Prefixed `_` because it is never instantiated directly.

| Method | Behaviour |
|---|---|
| `status_lines()` | Reads live telemetry from the DroneKit vehicle and formats it for the CLI |
| `arm_and_takeoff(alt)` | Blocks until armable → GUIDED mode → armed → `simple_takeoff` |
| `land()` | Switches to LAND mode (blocking mode wait) |
| `set_altitude(alt)` | Fire-and-forget `simple_goto` at same lat/lon, new altitude |
| `move_forward(m)` / `move_back(m)` | Projects distance onto lat/lon using current yaw (radians, 0=North, CW+); `simple_goto` |
| `rotate_left(°)` / `rotate_right(°)` | Sends `MAV_CMD_CONDITION_YAW` with relative-offset flag via `vehicle.send_mavlink` |

Blocking helpers (`_wait_for_condition`, `_wait_for_mode`, `_ensure_armed`) are only used during setup operations — never in steady-state flight commands that must not freeze the UI.

`connect()` is abstract; subclasses differ only in how they obtain the connection string.

---

## Concrete backends

### `DronekitSITLController`

Calls `dronekit_sitl.start_default()`, retrieves the connection string it allocates, and passes it to DroneKit's `connect()`. Optionally constructs a `GCSProxy` (when `gcs_port` is not `None`) and calls `proxy.start(vehicle)` after the vehicle is live.

Overrides `connection_details()` to append the GCS proxy target when active.

`close()` stops the proxy, closes the vehicle connection, then stops the SITL process — in that order.

### `DronekitPixhawkController`

Requires an explicit connection string at construction time. `connect()` calls DroneKit's `connect()` directly. `close()` is fully inherited — no SITL or proxy to tear down.

---

## GCS proxy — `GCSProxy`

`dronekit_version/gcs_proxy.py` forwards live MAVLink telemetry to QGroundControl over UDP with no MAVProxy dependency and no secondary connection to SITL.

**Mechanism:**

1. A UDP socket is created at construction and optionally configured with `SO_BROADCAST` (only when `gcs_host` is a broadcast address).
2. `start(vehicle)` registers a `'*'` wildcard message listener on the DroneKit vehicle object via `vehicle.add_message_listener('*', callback)`.
3. DroneKit fires the callback for every raw MAVLink frame it receives from SITL. The callback calls `message.get_msgbuf()` to get the original frame bytes and sends them to `gcs_host:gcs_port` via the UDP socket.
4. `stop()` removes the listener via `vehicle.remove_message_listener('*', callback)` and closes the UDP socket.

No extra threads, no second TCP connection to SITL. DroneKit's own reader thread drives the forwarding.

**Data flow:**
```
SITL ──TCP──► DroneKit reader thread
                    │  on_message('*')
                    ▼
               GCSProxy._forward()
                    │  sendto(gcs_host, gcs_port)
                    ▼
               QGroundControl (UDP)
```

---

## PyMAVLink stub — `PyMAVLinkController`

`dyopilot_version/dyopilot.py` is a concrete (instantiable) class where every method raises `NotImplementedError`. It exists as a placeholder for a future pymavlink-native backend that will replicate all DroneKit capabilities without the discontinued DroneKit/MAVProxy dependency chain.

---

## CLI — `drone_cli.py`

The terminal UI imports only `DroneController`. No backend detail leaks in.

**Startup sequence:**
1. `parse_args()` collects `--backend`, `--connect`, `--interval`, `--duration`, `--gcs-port`, `--gcs-host`.
2. Per-backend connection defaults are applied in `main()`: `tcp:127.0.0.1:5760` for `pixhawk`/`mavlink`; GCS proxy on `127.0.0.1:14550` for `sitl`. `--gcs-port 0` disables the proxy.
3. `build_controller()` is the only place that knows which concrete class to instantiate.
4. `run_cli()` calls `controller.connect()`, then hands off to `curses.wrapper`.

**Render loop (`cli_loop`):**
- `nodelay(True)` + 100 ms timeout — never hard-blocks.
- Every `--interval` seconds calls `render_screen()` to refresh telemetry.
- Keystrokes accumulate in a string buffer; Enter dispatches to `handle_command()`.
- All flight commands are fire-and-forget (except `takeoff` and `land` which block internally in the controller until safe state transitions complete).

**Screen layout:**
```
=== Vehicle snapshot ===
Mode / status / armed / altitude / location / attitude / velocity / battery

Connection: <string>
GCS Proxy: → <host>:<port>  (QGC ready)

Last command: <result>

Commands: takeoff <alt>, altitude <alt>, forward/back <m>, left/right <deg>, land, quit
> <buffer>
```
