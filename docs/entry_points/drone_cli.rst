drone_cli.py
============

Interactive curses console that shows live telemetry and accepts flight
commands. The same commands work on every backend because the CLI only talks
to :py:class:`drone_controller.DroneController`.

.. code-block:: bash

   python entry_points/drone_cli.py [--backend NAME] [--connect STRING]
                                    [--interval SECONDS] [--duration SECONDS]
                                    [--gcs-port PORT] [--gcs-host HOST]

Arguments
---------

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Argument
     - Default
     - Meaning
   * - ``--backend``
     - ``dronekit-sitl``
     - ``dronekit-sitl``, ``dronekit-pixhawk``, ``dyopilot-sitl`` or ``dyopilot-pixhawk``
   * - ``--connect``
     - ``tcp:127.0.0.1:5760`` (``*-pixhawk`` only)
     - Vehicle connection string, e.g. ``/dev/ttyUSB0``. The ``*-sitl`` backends start their own simulator and ignore it.
   * - ``--interval``
     - ``2.0``
     - Seconds between telemetry refreshes
   * - ``--duration``
     - run until quit
     - Optional time limit in seconds
   * - ``--gcs-port``
     - ``14550``
     - UDP port of the QGroundControl proxy; ``0`` disables it (``*-sitl`` only)
   * - ``--gcs-host``
     - ``127.0.0.1``
     - Machine running QGroundControl; ``255.255.255.255`` broadcasts to the LAN (``*-sitl`` only)

Which interpreter for which backend
-----------------------------------

.. list-table::
   :header-rows: 1

   * - Backend family
     - Python
     - Requirements file
   * - ``dronekit-*``
     - 3.7
     - ``dronekit_version/requirements-3.7.17.txt``
   * - ``dyopilot-*``
     - 3.12+
     - ``dyopilot_version/requirements.txt``

Running a ``dronekit-*`` backend on Python 3.10+ exits immediately with an
explanatory message instead of a traceback. The full two-virtualenv setup is in
:doc:`../guide/how`.

Console commands
----------------

``takeoff <alt>``, ``altitude <alt>``, ``forward <m>``, ``back <m>``,
``left <deg>``, ``right <deg>``, ``land``, ``quit``. Each command is described
in :doc:`../guide/how`.

How it works
------------

``entry_points/drone_cli.py`` puts the repo root on ``sys.path``, then
``build_controller()`` (a thin wrapper over
:py:func:`drone_console.create_controller`) imports only the selected backend. See
:doc:`../guide/arch` for the startup sequence and :doc:`../api/cli` for the
function reference.
