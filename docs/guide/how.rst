How it works
============

Starting the CLI
----------------

.. code-block:: bash

   python entry_points/drone_cli.py                                        # dronekit-sitl + QGC proxy on 127.0.0.1:14550 (Python 3.7)
   python entry_points/drone_cli.py --gcs-port 0                          # dronekit-sitl, proxy disabled
   python entry_points/drone_cli.py --backend dronekit-pixhawk            # Pixhawk via tcp:127.0.0.1:5760 (Python 3.7)
   python entry_points/drone_cli.py --backend dronekit-pixhawk --connect /dev/ttyUSB0
   python entry_points/drone_cli.py --backend dyopilot-sitl               # pymavlink + built-in SITL (Python 3.12+)
   python entry_points/drone_cli.py --backend dyopilot-pixhawk --connect /dev/ttyUSB0  # pymavlink + Pixhawk (Python 3.12+)
   python entry_points/drone_cli.py --interval 1.0                        # refresh telemetry every 1 s

``dronekit-*`` backends must be run under the Python 3.7 interpreter described below; ``dyopilot-*`` backends run on the Python 3.12 interpreter. Each backend is a fully self-contained process — no backend talks to another interpreter.

On launch the CLI:

1. Applies per-backend connection defaults when ``--connect`` is omitted.
2. Instantiates the selected backend controller.
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

- Removes the GCS proxy listener and closes the UDP socket (SITL only).
- Closes the DroneKit vehicle connection.
- Stops the SITL process (SITL only).

Backend selection
-----------------

==================== ============================================================================= ====================== ======
``--backend``        Connects to                                                                   ``--connect`` default  Python
==================== ============================================================================= ====================== ======
``dronekit-sitl``    dronekit-sitl subprocess (ArduCopter 3.3), driven via DroneKit's ``Vehicle``  assigned by SITL       3.7
``dronekit-pixhawk`` Physical Pixhawk over serial or TCP/UDP, driven via DroneKit's ``Vehicle``    ``tcp:127.0.0.1:5760`` 3.7
``dyopilot-sitl``    Same ArduCopter 3.3 SITL subprocess, driven via raw pymavlink/``mavutil``     assigned by SITL       3.12+
``dyopilot-pixhawk`` Physical Pixhawk over serial or TCP/UDP, driven via raw pymavlink/``mavutil`` ``tcp:127.0.0.1:5760`` 3.12+
==================== ============================================================================= ====================== ======

All backends expose the same CLI commands.

Two-interpreter setup
---------------------

The ``dronekit-*`` and ``dyopilot-*`` backends need two **separate virtual environments**, because they need two different Python versions — there is no single interpreter both can run under. Each backend is a fully self-contained process; nothing crosses between the two venvs at runtime.

.. _python-37-venv--dronekit-sitl--dronekit-pixhawk:

Python 3.7 venv — ``dronekit-sitl`` / ``dronekit-pixhawk``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Requires **Python 3.7** due to DroneKit compatibility (``dronekit==2.9.2`` uses ``collections.MutableMapping``, removed in Python 3.10). Defined in ``dronekit_version/requirements-3.7.17.txt``.

============================================ ======= ===============================================
Package                                      Version Purpose
============================================ ======= ===============================================
dronekit                                     2.9.2   High-level vehicle API
dronekit-sitl                                3.3.0   Bundles and launches ArduPilot SITL
pymavlink                                    2.4.8   Raw MAVLink message construction (yaw rotation)
pyserial                                     3.5     Serial port access for Pixhawk USB connections
Cython, future, lxml, monotonic, psutil, six various DroneKit transitive dependencies
============================================ ======= ===============================================

.. _python-312-venv--dyopilot-sitl--dyopilot-pixhawk:

Python 3.12+ venv — ``dyopilot-sitl`` / ``dyopilot-pixhawk``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Defined in ``dyopilot_version/requirements.txt``. No DroneKit anywhere in the import path.

+---------------+---------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Package       | Version | Purpose                                                                                                                                                                                   |
+===============+=========+===========================================================================================================================================================================================+
| dronekit-sitl | 3.3.0   | Bundles and launches ArduPilot SITL (same package as above — but its own runtime code never imports ``dronekit``, only its unused ``forwarder.py`` submodule does, so it works fine here) |
+---------------+---------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| pymavlink     | 2.4.49  | All MAVLink message construction and parsing                                                                                                                                              |
+---------------+---------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| pyserial      | 3.5     | Serial port access for Pixhawk USB connections                                                                                                                                            |
+---------------+---------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

``pip install``\ ing this file will also pull in ``dronekit==2.9.2`` as a transitive dependency declared by ``dronekit-sitl``'s own package metadata — you'll see it in ``pip list``. It is never imported anywhere in ``dyopilot_version/`` and is harmless dead weight; don't be alarmed by it, and don't try to ``import dronekit`` yourself in this venv (it will fail on 3.10+, same as everywhere else).

Choosing the wrong interpreter for a backend fails fast: running a ``dronekit-*`` backend under Python 3.10+ prints an actionable error instead of a raw traceback (see ``build_controller()`` in ``entry_points/drone_cli.py``).
