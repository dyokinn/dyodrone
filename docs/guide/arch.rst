Architecture
============

Overview
--------

Four layers: an abstract controller interface, two **drivers** (flight-control libraries) that implement it, **targets** that supply the vehicle connection, and front ends (a terminal CLI and a web console) that depend only on the abstract interface.

::

   src/dyodrone/
   ├── core/
   │   ├── controller.py      ← DroneController  (ABC)
   │   ├── commands.py        ← handle_command(), shared by both front ends
   │   ├── targets.py         ← Target, SitlTarget, ExternalTarget
   │   ├── proxy.py           ← GCSProxy         (UDP forwarder to QGroundControl)
   │   └── factory.py         ← create_controller(driver, target, …)
   ├── drivers/
   │   ├── dronekit_driver.py ← DroneKitController   (Python 3.7 only)
   │   ├── dyopilot_driver.py ← DyopilotController   (pymavlink, Python 3.12+)
   │   └── dyopilot_reader.py ← MAVLinkReader        (background message thread)
   ├── cli.py                 ← curses CLI    (dyodrone-cli, python -m dyodrone)
   └── gui/                   ← web console   (dyodrone-gui): session, server, static page

A controller is *driver × target*: ``DroneKitController(target)`` or ``DyopilotController(target)``. The target only produces a connection string and tears down whatever it started, so the four combinations need two controller classes, not four.

``GCSProxy`` has no DroneKit dependency; it only needs a ``forward(raw_bytes)`` callback, which ``DroneKitController`` (via a DroneKit message listener) and ``DyopilotController`` (via ``MAVLinkReader``'s ``on_frame`` callback) can both supply.

.. _abstract-base--dronecontroller:

Abstract base — ``DroneController``
-----------------------------------

``dyodrone/core/controller.py`` defines the only contract the front ends ever touch. Every flight operation is ``@abstractmethod``. There is no driver- or target-specific state here.

Two concrete helpers are provided so subclasses don't have to override them unless they have extra information to surface:

- ``__enter__`` / ``__exit__`` — context manager that calls ``connect()`` / ``close()``.
- ``connection_details() -> List[str]`` — returns a list of human-readable connection lines for the CLI screen. Default implementation reads ``active_connection``. Subclasses append extra lines (e.g. GCS proxy host/port).

Targets — ``Target``
--------------------

``core/targets.py``. A target answers two questions: *what connection string do I connect to?* (``acquire()``) and *what do I stop when done?* (``release()``, safe to call twice).

``SitlTarget``
   Starts the ArduCopter 3.3 simulator with ``dronekit_sitl.start_default()`` (imported lazily) and returns the connection string it allocates. ``release()`` stops the simulator. ``dronekit_sitl``'s own runtime code (``start_default``, ``connection_string``, ``stop``) never imports ``dronekit`` — only its unused ``forwarder.py`` does — so this works on Python 3.12 even though DroneKit itself does not.

``ExternalTarget(connection)``
   Returns the string you gave it (``/dev/ttyUSB0``, ``tcp:host:5760``, an already-running simulator) and owns nothing, so ``release()`` is a no-op. An empty string is rejected.

``make_target(name, connection)`` builds either one from the names ``"sitl"`` and ``"pixhawk"``.

.. _dronekit-driver--dronekitcontroller:

DroneKit driver — ``DroneKitController``
----------------------------------------

``drivers/dronekit_driver.py`` implements all flight logic on top of DroneKit's ``Vehicle``. Constructed as ``DroneKitController(target, proxy=None, wait_ready=True)``.

======================================== =========================================================================================
Method                                   Behaviour
======================================== =========================================================================================
``connect()``                            ``target.acquire()`` → DroneKit ``connect()`` → ``proxy.start(vehicle)`` if a proxy was given. Any failure releases the target before re-raising.
``close()``                              Stops the proxy, closes the vehicle, releases the target — in that order.
``status_lines()``                       Reads live telemetry from the DroneKit vehicle and formats it for the CLI
``arm_and_takeoff(alt)``                 Blocks until armable → GUIDED mode → armed → ``simple_takeoff``
``land()``                               Switches to LAND mode (blocking mode wait)
``set_altitude(alt)``                    Fire-and-forget ``simple_goto`` at same lat/lon, new altitude
``move_forward(m)`` / ``move_back(m)``   Projects distance onto lat/lon using current yaw (radians, 0=North, CW+); ``simple_goto``
``rotate_left(°)`` / ``rotate_right(°)`` Sends ``MAV_CMD_CONDITION_YAW`` with relative-offset flag via ``vehicle.send_mavlink``
======================================== =========================================================================================

Blocking helpers (``_wait_for_condition``, ``_wait_for_mode``, ``_ensure_armed``) are only used during setup operations — never in steady-state flight commands that must not freeze the UI.

.. _gcs-proxy--gcsproxy:

GCS proxy — ``GCSProxy``
------------------------

``core/proxy.py`` forwards live MAVLink telemetry to QGroundControl over UDP with no MAVProxy dependency and no secondary connection to SITL.

**Mechanism:**

1. A UDP socket is created at construction and optionally configured with ``SO_BROADCAST`` (only when ``gcs_host`` is a broadcast address).
2. ``start(vehicle)`` registers a ``'*'`` wildcard message listener on the DroneKit vehicle object via ``vehicle.add_message_listener('*', callback)``.
3. DroneKit fires the callback for every raw MAVLink frame it receives from SITL. The callback calls ``message.get_msgbuf()`` to get the original frame bytes and sends them to ``gcs_host:gcs_port`` via the UDP socket.
4. ``stop()`` removes the listener via ``vehicle.remove_message_listener('*', callback)`` and closes the UDP socket.

No extra threads, no second TCP connection to SITL. DroneKit's own reader thread drives the forwarding; the dyopilot driver calls ``GCSProxy.forward(raw_bytes)`` from its reader thread instead.

**Data flow:**

::

   SITL ──TCP──► DroneKit reader thread
                       │  on_message('*')
                       ▼
                  GCSProxy._forward()
                       │  sendto(gcs_host, gcs_port)
                       ▼
                  QGroundControl (UDP)

.. _dyopilot-driver--dyopilotcontroller:

dyopilot driver — ``DyopilotController``
----------------------------------------

``drivers/dyopilot_driver.py`` implements the same flight-operation contract as ``DroneKitController``, but on raw pymavlink/``mavutil`` calls instead of DroneKit's ``Vehicle`` API — no DroneKit dependency anywhere in the driver, which is what lets it run on a current Python interpreter (3.12+) instead of the 3.7 DroneKit requires. Constructed as ``DyopilotController(target, proxy=None, heartbeat_timeout=30)``.

pymavlink has no listener dispatch of its own — nothing populates ``master.messages``/``master.flightmode`` unless something keeps calling ``recv_msg()``. ``drivers/dyopilot_reader.py``'s ``MAVLinkReader`` is a background daemon thread that does this, and optionally forwards every raw frame to a sink (``GCSProxy.forward``).

``connect()`` acquires the target and calls ``_open_master(conn_str, proxy)``, which does "connect mavutil → wait for heartbeat → request all data streams → start ``MAVLinkReader``". Any failure (including a missing heartbeat) releases the target and re-raises, so a half-started simulator is never left behind. ``close()`` stops the proxy, the reader and the connection, then releases the target.

Mode changes (``_wait_for_mode``/``_set_mode``) deliberately do **not** use mavutil's ``set_mode_apm()``. Current pymavlink (2.4.49) implements it by sending ``MAV_CMD_DO_SET_MODE`` via ``COMMAND_LONG``, which the ArduCopter 3.3 SITL binary ``dronekit_sitl`` bundles rejects outright (``COMMAND_ACK result=3``, unsupported) — that firmware predates ``COMMAND_LONG``-based mode changes and only understands the legacy ``SET_MODE`` message. ``_set_mode()`` looks up the mode via ``master.mode_mapping()`` and sends ``master.mav.set_mode_send(...)`` directly instead. This was caught by running a live SITL end-to-end, not by inspection — ``arm_and_takeoff`` silently timed out waiting for GUIDED mode until it was fixed — and is pinned by a regression test.

======================================== ===================================================================================
Method                                   Behaviour
======================================== ===================================================================================
``status_lines()``                       Reads live telemetry out of ``master.messages`` and formats it for the CLI
``arm_and_takeoff(alt)``                 Blocks until GPS 3D fix seen → GUIDED mode → armed → ``MAV_CMD_NAV_TAKEOFF``
``land()``                               Switches to LAND mode (blocking mode wait)
``set_altitude(alt)``                    Fire-and-forget ``SET_POSITION_TARGET_GLOBAL_INT`` at same lat/lon, new altitude
``move_forward(m)`` / ``move_back(m)``   Projects distance onto lat/lon using current yaw; same math as ``DroneKitController``
``rotate_left(°)`` / ``rotate_right(°)`` Sends ``MAV_CMD_CONDITION_YAW`` with relative-offset flag via ``command_long_send``
======================================== ===================================================================================

.. _cli--dyodrone-cli:

CLI — ``dyodrone/cli.py``
-------------------------

The terminal UI imports only ``DroneController``. No driver or target detail leaks in.

**Startup sequence:**

1. ``parse_args()`` collects ``--driver``, ``--target``, ``--connect``, ``--interval``, ``--duration``, ``--gcs-port``, ``--gcs-host``. ``--driver`` defaults to the one that can run on this interpreter (``dronekit`` on Python < 3.10, otherwise ``dyopilot``).
2. ``build_controller()`` resolves the proxy default — port 14550 for ``--target sitl``, off for ``pixhawk`` unless ``--gcs-port`` is given (``0`` disables it) — and the Pixhawk connection default ``tcp:127.0.0.1:5760``.
3. ``create_controller()`` in ``core/factory.py`` is the only place that knows which concrete class to instantiate. It imports each driver lazily, inside the matching branch, rather than at the top of the file — only ``--driver dronekit`` ever imports DroneKit, so choosing ``dyopilot`` never touches it. For ``dronekit`` it also gates on ``sys.version_info`` and raises an actionable error instead of a raw ``AttributeError`` on Python 3.10+ (see :doc:`how`).
4. ``run_cli()`` calls ``controller.connect()``, then hands off to ``curses.wrapper``.

**Render loop (``cli_loop``):**

- ``nodelay(True)`` + 100 ms timeout — never hard-blocks.
- Every ``--interval`` seconds calls ``render_screen()`` to refresh telemetry.
- Keystrokes accumulate in a string buffer; Enter dispatches to ``handle_command()`` (shared with the web console in ``core/commands.py``).
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
