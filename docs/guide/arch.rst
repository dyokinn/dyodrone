Architecture
============

Overview
--------

Three layers: an abstract controller interface, concrete backend implementations, and a terminal CLI that depends only on the abstract interface.

::

   drone_controller.py               ← DroneController  (ABC)
   │
   ├── dronekit_version/                    (Python 3.7 — see docs/guide/how.rst)
   │   ├── dronekit_controller.py    ← _DroneKitBase     (shared flight logic)
   │   ├── dronekit_sitl_controller.py  ← DronekitSITLController
   │   ├── dronekit_pixhawk_controller.py ← DronekitPixhawkController
   │   └── gcs_proxy.py              ← GCSProxy          (UDP forwarder, backend-agnostic)
   │
   ├── dyopilot_version/                    (Python 3.12+ — see docs/guide/how.rst)
   │   ├── pymavlink_reader.py       ← MAVLinkReader     (background message-cache thread)
   │   ├── dyopilot_controller.py    ← _PyMAVLinkBase    (shared flight logic)
   │   ├── dyopilot_sitl_controller.py  ← DyopilotSITLController
   │   └── dyopilot_pixhawk_controller.py ← DyopilotPixhawkController
   │
   └── entry_points/
       ├── drone_cli.py              ← curses CLI        (backend-agnostic)
       └── build_docs.sh             ← builds these docs

``dyopilot_version`` reuses ``dronekit_version/gcs_proxy.py`` directly — ``GCSProxy`` has no DroneKit dependency, it only needs a ``forward(raw_bytes)`` callback, which both ``_DroneKitBase`` (via a DroneKit message listener) and ``_PyMAVLinkBase`` (via ``MAVLinkReader``'s ``on_frame`` callback) can supply. There's no need for a separate copy per backend family.

.. _abstract-base--dronecontroller:

Abstract base — ``DroneController``
-----------------------------------

``drone_controller.py`` defines the only contract the CLI ever touches. Every flight operation is ``@abstractmethod``. There is no backend-specific state here.

Two concrete helpers are provided so subclasses don't have to override them unless they have extra information to surface:

- ``__enter__`` / ``__exit__`` — context manager that calls ``connect()`` / ``close()``.
- ``connection_details() -> List[str]`` — returns a list of human-readable connection lines for the CLI screen. Default implementation reads ``active_connection``. Subclasses append extra lines (e.g. GCS proxy host/port).

.. _dronekit-shared-logic--_dronekitbase:

DroneKit shared logic — ``_DroneKitBase``
-----------------------------------------

``dronekit_version/dronekit_controller.py`` implements all flight logic on top of DroneKit. Prefixed ``_`` because it is never instantiated directly.

======================================== =========================================================================================
Method                                   Behaviour
======================================== =========================================================================================
``status_lines()``                       Reads live telemetry from the DroneKit vehicle and formats it for the CLI
``arm_and_takeoff(alt)``                 Blocks until armable → GUIDED mode → armed → ``simple_takeoff``
``land()``                               Switches to LAND mode (blocking mode wait)
``set_altitude(alt)``                    Fire-and-forget ``simple_goto`` at same lat/lon, new altitude
``move_forward(m)`` / ``move_back(m)``   Projects distance onto lat/lon using current yaw (radians, 0=North, CW+); ``simple_goto``
``rotate_left(°)`` / ``rotate_right(°)`` Sends ``MAV_CMD_CONDITION_YAW`` with relative-offset flag via ``vehicle.send_mavlink``
======================================== =========================================================================================

Blocking helpers (``_wait_for_condition``, ``_wait_for_mode``, ``_ensure_armed``) are only used during setup operations — never in steady-state flight commands that must not freeze the UI.

``connect()`` is abstract; subclasses differ only in how they obtain the connection string.

Concrete backends
-----------------

``DronekitSITLController``
~~~~~~~~~~~~~~~~~~~~~~~~~~

Calls ``dronekit_sitl.start_default()``, retrieves the connection string it allocates, and passes it to DroneKit's ``connect()``. Optionally constructs a ``GCSProxy`` (when ``gcs_port`` is not ``None``) and calls ``proxy.start(vehicle)`` after the vehicle is live.

Overrides ``connection_details()`` to append the GCS proxy target when active.

``close()`` stops the proxy, closes the vehicle connection, then stops the SITL process — in that order.

``DronekitPixhawkController``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Requires an explicit connection string at construction time. ``connect()`` calls DroneKit's ``connect()`` directly. ``close()`` is fully inherited — no SITL or proxy to tear down.

.. _gcs-proxy--gcsproxy:

GCS proxy — ``GCSProxy``
------------------------

``dronekit_version/gcs_proxy.py`` forwards live MAVLink telemetry to QGroundControl over UDP with no MAVProxy dependency and no secondary connection to SITL.

**Mechanism:**

1. A UDP socket is created at construction and optionally configured with ``SO_BROADCAST`` (only when ``gcs_host`` is a broadcast address).
2. ``start(vehicle)`` registers a ``'*'`` wildcard message listener on the DroneKit vehicle object via ``vehicle.add_message_listener('*', callback)``.
3. DroneKit fires the callback for every raw MAVLink frame it receives from SITL. The callback calls ``message.get_msgbuf()`` to get the original frame bytes and sends them to ``gcs_host:gcs_port`` via the UDP socket.
4. ``stop()`` removes the listener via ``vehicle.remove_message_listener('*', callback)`` and closes the UDP socket.

No extra threads, no second TCP connection to SITL. DroneKit's own reader thread drives the forwarding.

**Data flow:**

::

   SITL ──TCP──► DroneKit reader thread
                       │  on_message('*')
                       ▼
                  GCSProxy._forward()
                       │  sendto(gcs_host, gcs_port)
                       ▼
                  QGroundControl (UDP)

.. _pymavlink-shared-logic--_pymavlinkbase:

PyMAVLink shared logic — ``_PyMAVLinkBase``
-------------------------------------------

``dyopilot_version/dyopilot_controller.py`` implements the same flight-operation contract as ``_DroneKitBase``, but on raw pymavlink/``mavutil`` calls instead of DroneKit's ``Vehicle`` API — no DroneKit dependency anywhere in ``dyopilot_version/``, which is what lets it run on a current Python interpreter (3.12+) instead of the 3.7 DroneKit requires.

pymavlink has no listener dispatch of its own — nothing populates ``master.messages``/``master.flightmode`` unless something keeps calling ``recv_msg()``. ``pymavlink_reader.py``'s ``MAVLinkReader`` is a background daemon thread that does this, and optionally forwards every raw frame to a sink (e.g. ``GCSProxy.forward``).

A shared ``_open_master(conn_str, proxy=None)`` helper does "connect mavutil → wait for heartbeat → request all data streams → start ``MAVLinkReader``" — both concrete subclasses call it from their own ``connect()``, the same way both DroneKit subclasses differ only in how they obtain a connection string.

Mode changes (``_wait_for_mode``/``_set_mode``) deliberately do **not** use mavutil's ``set_mode_apm()``. Current pymavlink (2.4.49) implements it by sending ``MAV_CMD_DO_SET_MODE`` via ``COMMAND_LONG``, which the ArduCopter 3.3 SITL binary ``dronekit_sitl`` bundles rejects outright (``COMMAND_ACK result=3``, unsupported) — that firmware predates ``COMMAND_LONG``-based mode changes and only understands the legacy ``SET_MODE`` message. ``_set_mode()`` looks up the mode via ``master.mode_mapping()`` and sends ``master.mav.set_mode_send(...)`` directly instead. This was caught by running a live SITL end-to-end during implementation, not by inspection — ``arm_and_takeoff`` silently timed out waiting for GUIDED mode until this was fixed.

======================================== ===================================================================================
Method                                   Behaviour
======================================== ===================================================================================
``status_lines()``                       Reads live telemetry out of ``master.messages`` and formats it for the CLI
``arm_and_takeoff(alt)``                 Blocks until GPS 3D fix seen → GUIDED mode → armed → ``MAV_CMD_NAV_TAKEOFF``
``land()``                               Switches to LAND mode (blocking mode wait)
``set_altitude(alt)``                    Fire-and-forget ``SET_POSITION_TARGET_GLOBAL_INT`` at same lat/lon, new altitude
``move_forward(m)`` / ``move_back(m)``   Projects distance onto lat/lon using current yaw; same math as ``_DroneKitBase``
``rotate_left(°)`` / ``rotate_right(°)`` Sends ``MAV_CMD_CONDITION_YAW`` with relative-offset flag via ``command_long_send``
======================================== ===================================================================================

``DyopilotSITLController``
~~~~~~~~~~~~~~~~~~~~~~~~~~

Calls ``dronekit_sitl.start_default()`` directly, in-process — ``dronekit_sitl``'s own runtime code (``start_default``, ``connection_string``, ``stop``) never imports ``dronekit``, only its unused ``forwarder.py`` submodule does, so this works fine on Python 3.12 even though ``dronekit`` itself is broken there. Retrieves the connection string it allocates and passes it to ``_open_master()``. Optionally constructs a ``GCSProxy`` exactly like ``DronekitSITLController`` does.

``close()`` stops the proxy, closes the reader/master (via ``super().close()``), then stops the SITL process — same order as ``DronekitSITLController``.

``DyopilotPixhawkController``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Requires an explicit connection string at construction time. ``connect()`` calls ``_open_master()`` directly — no SITL, no proxy. ``close()`` is fully inherited from ``_PyMAVLinkBase`` — no extra resources to release. Mirrors ``DronekitPixhawkController`` exactly.

.. _cli--drone_clipy:

CLI — ``entry_points/drone_cli.py``
-----------------------------------

The terminal UI imports only ``DroneController``. No backend detail leaks in.

**Startup sequence:**

1. ``parse_args()`` collects ``--backend``, ``--connect``, ``--interval``, ``--duration``, ``--gcs-port``, ``--gcs-host``.
2. Per-backend connection defaults are applied in ``main()``: ``tcp:127.0.0.1:5760`` for ``dronekit-pixhawk``/``dyopilot-pixhawk``; GCS proxy on ``127.0.0.1:14550`` for ``dronekit-sitl``/``dyopilot-sitl``. ``--gcs-port 0`` disables the proxy.
3. ``build_controller()`` is the only place that knows which concrete class to instantiate. It imports each backend's module lazily, inside the matching branch, rather than at the top of the file — a ``dronekit-*`` selection is the only path that ever imports DroneKit, so choosing a ``dyopilot-*`` backend never touches it. For ``dronekit-*`` backends it also gates on ``sys.version_info`` and raises an actionable error instead of a raw ``AttributeError`` on Python 3.10+ (see :doc:`how`).
4. ``run_cli()`` calls ``controller.connect()``, then hands off to ``curses.wrapper``.

**Render loop (``cli_loop``):**

- ``nodelay(True)`` + 100 ms timeout — never hard-blocks.
- Every ``--interval`` seconds calls ``render_screen()`` to refresh telemetry.
- Keystrokes accumulate in a string buffer; Enter dispatches to ``handle_command()``.
- All flight commands are fire-and-forget (except ``takeoff`` and ``land`` which block internally in the controller until safe state transitions complete).

**Screen layout:**

::

   === Vehicle snapshot ===
   Mode / status / armed / altitude / location / attitude / velocity / battery

   Connection: <string>
   GCS Proxy: → <host>:<port>  (QGC ready)

   Last command: <result>

   Commands: takeoff <alt>, altitude <alt>, forward/back <m>, left/right <deg>, land, quit
   > <buffer>
