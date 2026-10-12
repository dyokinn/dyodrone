How it works
============

Starting the CLI
----------------

.. code-block:: bash

   dyodrone-cli                                          # default driver for this Python, simulator, QGC proxy on 127.0.0.1:14550
   dyodrone-cli --gcs-port 0                             # simulator, proxy disabled
   dyodrone-cli --target pixhawk                         # Pixhawk via tcp:127.0.0.1:5760
   dyodrone-cli --target pixhawk --connect /dev/ttyUSB0
   dyodrone-cli --driver dyopilot --target sitl          # pymavlink + built-in simulator (Python 3.12+)
   dyodrone-cli --driver dronekit --target pixhawk       # DroneKit + Pixhawk (Python 3.7)
   dyodrone-cli --interval 1.0                           # refresh telemetry every 1 s
   python -m dyodrone                                    # same as dyodrone-cli

Prefer a browser? ``dyodrone-gui`` offers the same commands with a connection toggle — see :doc:`../entry_points/dyodrone_gui`.

You pick a **driver** (the flight-control library) and a **target** (what it connects to); see :ref:`drivers-and-targets`. ``--driver dronekit`` must be run under the Python 3.7 interpreter and ``--driver dyopilot`` on Python 3.12; each process is fully self-contained — nothing talks to another interpreter. Without ``--driver`` the CLI picks the one that can run on the current Python.

On launch the CLI:

1. Resolves defaults: the Pixhawk connection string, and the QGC proxy port (on for the simulator, off for Pixhawk).
2. Builds the controller for the chosen driver and target.
3. Calls ``controller.connect()`` — blocks until the vehicle (or SITL) is ready.
4. Prints the connection string, then enters the curses screen.

For QGC integration details see :doc:`proxy`.

The curses screen
-----------------

Refreshes every ``--interval`` seconds (default 2 s) and immediately after every keystroke.

================== =========================================================================================================
Section            Content
================== =========================================================================================================
Vehicle snapshot   Mode, system status, armable, armed, altitude, GPS location, attitude (roll/pitch/yaw), velocity, battery
Connection details Vehicle connection string; GCS proxy target when active
Last command       Result of the most recently submitted command
Command line       Fixed hint + input prompt (``>``)
================== =========================================================================================================

Typing builds a command in the buffer. Backspace removes the last character. Enter submits.

Commands
--------

``takeoff <altitude>``
~~~~~~~~~~~~~~~~~~~~~~

Arms and climbs to the requested altitude in metres AGL.

1. Polls until the autopilot reports ``is_armable`` (up to 60 s).
2. Sets mode to GUIDED; retries every second until confirmed.
3. Sets ``vehicle.armed = True``; retries until confirmed.
4. Calls ``simple_takeoff(altitude)``.

The CLI does not block during the climb — telemetry keeps refreshing while the vehicle rises.

::

   > takeoff 10

``land``
~~~~~~~~

Switches to LAND mode. The autopilot descends and disarms automatically.

::

   > land

``altitude <metres>``
~~~~~~~~~~~~~~~~~~~~~

Changes target altitude while airborne. Fire-and-forget — the autopilot climbs or descends in the background.

Requires the vehicle to be armed. Switches to GUIDED mode first if needed.

::

   > altitude 20

.. _forward-metres--back-metres:

``forward <metres>`` / ``back <metres>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Moves the drone relative to the direction it is currently facing.

Heading is read from ``vehicle.attitude.yaw`` (radians, 0 = North, CW positive). The distance is projected onto lat/lon offsets:

::

   d_lat = distance × cos(yaw) / 111 320
   d_lon = distance × sin(yaw) / (111 320 × cos(lat))

``back`` negates both offsets. Current altitude is preserved. Fire-and-forget.

::

   > forward 5
   > back 3

.. _left-degrees--right-degrees:

``left <degrees>`` / ``right <degrees>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Rotates the drone in place relative to its current heading using ``MAV_CMD_CONDITION_YAW`` with the relative-offset flag.

``left`` = counter-clockwise, ``right`` = clockwise.

::

   > right 90
   > left 45

.. _quit--exit:

``quit`` / ``exit``
~~~~~~~~~~~~~~~~~~~

Closes the curses UI cleanly. The ``finally`` block calls ``controller.close()``, which:

- Stops the GCS proxy and closes its UDP socket (when one is running).
- Closes the vehicle connection.
- Stops the simulator process (``--target sitl`` only).

.. _drivers-and-targets:

Drivers and targets
-------------------

Two independent choices:

.. list-table::
   :header-rows: 1
   :widths: 14 30 56

   * - Choice
     - Values
     - Meaning
   * - ``--driver``
     - ``dronekit``
     - Flight logic on DroneKit's ``Vehicle`` API. **Python 3.7 only.**
   * -
     - ``dyopilot``
     - Flight logic on raw pymavlink/``mavutil``. Python 3.12+ (also runs on 3.7).
   * - ``--target``
     - ``sitl``
     - Starts the bundled ArduCopter 3.3 simulator and connects to it.
   * -
     - ``pixhawk``
     - Connects to ``--connect`` (default ``tcp:127.0.0.1:5760``): a board on serial,
       a TCP/UDP endpoint, or an already-running simulator.

Any driver works with any target, so there are four combinations, all with the same
commands. The driver decides which Python environment you need; the target only decides where the
connection string comes from.

Two-interpreter setup
---------------------

``--driver dronekit`` and ``--driver dyopilot`` need two **separate virtual environments**, because they need two different Python versions — there is no single interpreter DroneKit and a current pymavlink can both run under. Each process is self-contained; nothing crosses between the two environments at runtime.

.. list-table::
   :header-rows: 1

   * - Environment
     - Python
     - Install
   * - DroneKit
     - 3.7
     - ``pip install -e ".[dronekit]"``
   * - dyopilot
     - 3.12+
     - ``pip install -e ".[dyopilot]"``

``dronekit==2.9.2`` uses ``collections.MutableMapping``, removed in Python 3.10, so the DroneKit environment must be 3.7. The dyopilot environment never imports DroneKit. ``dronekit-sitl`` declares ``dronekit`` as a dependency, so ``pip`` installs it there too; it is never imported and is harmless dead weight (don't ``import dronekit`` yourself in that environment). Package lists and pins are in :doc:`../project/dependencies`; step-by-step setup is in :doc:`installation`.

Choosing the wrong interpreter fails fast: ``--driver dronekit`` under Python 3.10+ prints an actionable error instead of a raw traceback (see ``create_controller()`` in ``dyodrone.core.factory``).
