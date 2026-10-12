Glossary
========

.. glossary::

   AGL
      Above ground level. The CLI reports altitude relative to the take-off
      point, not sea level.

   ArduCopter
      The ArduPilot firmware for multirotors. The bundled simulator is
      ArduCopter 3.3.

   COMMAND_LONG
      A MAVLink message carrying a numbered command (for example
      ``MAV_CMD_NAV_TAKEOFF``, ``MAV_CMD_CONDITION_YAW``) and up to seven
      parameters. The vehicle answers with ``COMMAND_ACK``.

   DroneKit
      A Python library that wraps MAVLink in a ``Vehicle`` object. Unmaintained
      and limited to Python 3.7 here.

   dyopilot
      This project's pymavlink-based flight code (``dyopilot_version``),
      which replaces DroneKit and runs on current Python.

   GCS
      Ground control station — software such as QGroundControl that displays
      telemetry from the vehicle.

   GUIDED
      ArduCopter flight mode in which the vehicle accepts position and
      altitude targets from software. Required for ``takeoff``, ``altitude``,
      ``forward``/``back`` and ``left``/``right``.

   HEARTBEAT
      The periodic MAVLink message a vehicle sends to announce itself. A
      backend is "connected" once it has received one.

   LAND
      Flight mode that descends and disarms automatically.

   MAVLink
      The lightweight message protocol between ground software and an
      autopilot.

   mavutil
      pymavlink's connection helper. ``master`` in the dyopilot code is a
      ``mavutil`` connection object.

   Pixhawk
      A common flight-controller board running ArduPilot or PX4. The
      ``*-pixhawk`` backends connect to it over serial, TCP or UDP.

   pymavlink
      The Python MAVLink library used directly by dyopilot.

   SET_MODE
      The legacy MAVLink message for changing flight mode, still the one the
      bundled ArduCopter 3.3 understands.

   SITL
      Software in the loop — the real autopilot firmware compiled to run on a
      PC against a simulated vehicle. ``dronekit_sitl`` downloads and launches
      it.

   STABILIZE
      ArduCopter's default manual-style mode at power-up; the simulator starts here.
