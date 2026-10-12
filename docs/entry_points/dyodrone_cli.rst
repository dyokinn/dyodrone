dyodrone-cli
============

Interactive curses console that shows live telemetry and accepts flight
commands. The same commands work with every driver and target because the CLI
only talks to :py:class:`dyodrone.core.controller.DroneController`.

.. code-block:: bash

   dyodrone-cli [--driver {dronekit,dyopilot}] [--target {sitl,pixhawk}]
                [--connect STRING] [--interval SECONDS] [--duration SECONDS]
                [--gcs-port PORT] [--gcs-host HOST]
   python -m dyodrone ...          # identical

Arguments
---------

.. list-table::
   :header-rows: 1
   :widths: 20 24 56

   * - Argument
     - Default
     - Meaning
   * - ``--driver``
     - by interpreter
     - ``dronekit`` (Python 3.7 only) or ``dyopilot`` (pymavlink). Defaults to
       ``dronekit`` on Python < 3.10 and ``dyopilot`` otherwise.
   * - ``--target``
     - ``sitl``
     - ``sitl`` starts the built-in simulator; ``pixhawk`` connects to ``--connect``.
   * - ``--connect``
     - ``tcp:127.0.0.1:5760``
     - Connection string for ``--target pixhawk``, e.g. ``/dev/ttyUSB0``. Ignored for ``sitl``.
   * - ``--interval``
     - ``2.0``
     - Seconds between telemetry refreshes
   * - ``--duration``
     - run until quit
     - Optional time limit in seconds
   * - ``--gcs-port``
     - 14550 for ``sitl``, off for ``pixhawk``
     - UDP port of the QGroundControl proxy; ``0`` disables it. Works with either target.
   * - ``--gcs-host``
     - ``127.0.0.1``
     - Machine running QGroundControl; ``255.255.255.255`` broadcasts to the LAN

Which interpreter for which driver
----------------------------------

.. list-table::
   :header-rows: 1

   * - Driver
     - Python
     - Install
   * - ``dronekit``
     - 3.7
     - ``pip install -e ".[dronekit]"``
   * - ``dyopilot``
     - 3.12+
     - ``pip install -e ".[dyopilot]"``

Running ``--driver dronekit`` on Python 3.10+ exits immediately with an
explanatory message instead of a traceback. The full two-environment setup is in
:doc:`../guide/installation`.

Console commands
----------------

``takeoff <alt>``, ``altitude <alt>``, ``forward <m>``, ``back <m>``,
``left <deg>``, ``right <deg>``, ``land``, ``quit``. Each command is described
in :doc:`../guide/how`.

How it works
------------

``build_controller()`` (a thin wrapper over
:py:func:`dyodrone.core.factory.create_controller`) imports only the selected
driver. See :doc:`../guide/arch` for the startup sequence and
:doc:`../api/cli` for the function reference.
