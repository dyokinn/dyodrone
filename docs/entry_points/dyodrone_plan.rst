dyodrone-plan
=============

Runs a :doc:`flight plan <../guide/plans>` with no UI: connect, fly it step by
step (each step verified by telemetry), disconnect.

.. code-block:: bash

   dyodrone-plan plan.txt                          # default driver for this Python, simulator
   dyodrone-plan plan.txt --target pixhawk --connect /dev/ttyUSB0
   dyodrone-plan plan.txt --dry-run                # validate and show what each step expects

Arguments
---------

.. list-table::
   :header-rows: 1
   :widths: 24 22 54

   * - Argument
     - Default
     - Meaning
   * - ``plan``
     - (required)
     - Path to the plan text file
   * - ``--driver``
     - by interpreter
     - ``dronekit`` (Python 3.7) or ``dyopilot``
   * - ``--target``
     - ``sitl``
     - ``sitl`` or ``pixhawk``
   * - ``--connect``
     - ``tcp:127.0.0.1:5760``
     - Connection string for ``--target pixhawk``
   * - ``--gcs-port`` / ``--gcs-host``
     - 14550 for sitl, off for pixhawk
     - QGroundControl proxy, as in :doc:`dyodrone_cli`
   * - ``--poll``
     - ``3``
     - Seconds between telemetry checks while a command runs
   * - ``--margin``
     - ``0.10``
     - Allowed error as a fraction of the commanded amount
   * - ``--step-timeout``
     - ``120``
     - Seconds before a step that has not completed fails the plan
   * - ``--dry-run``
     - off
     - Validate and print the steps and expectations; do not connect

Output and exit codes
---------------------

Progress is printed as the plan runs:

.. code-block:: text

   [1/4] takeoff 10: sending
   [1/4] takeoff 10: waiting — alt 8.5/10 m (±1.0)
   [1/4] takeoff 10: done — alt 9.9/10 m (±1.0)
   [2/4] forward 15: sending
   ...
   plan: done — plan complete

.. list-table::
   :header-rows: 1

   * - Exit code
     - Meaning
   * - 0
     - the whole plan completed
   * - 1
     - a step failed or timed out, the plan was stopped (Ctrl-C / SIGTERM), or the
       vehicle or driver was unavailable
   * - 2
     - the plan file is unreadable or invalid (errors are listed with line numbers)

The connection (and any simulator) is closed in every case. Ctrl-C stops issuing
commands; it does not land the vehicle.
