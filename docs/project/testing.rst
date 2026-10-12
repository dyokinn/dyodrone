Testing
=======

The suite is ``pytest`` under ``tests/``, with one folder per layer. Unit tests
need no hardware and no simulator; they run in about two seconds on both Python
3.12 and 3.7.

.. code-block:: bash

   pip install -e ".[dyopilot,test]" && pytest      # one environment
   tox                                              # 3.12 and 3.7
   pytest -m sitl                                   # live simulator (opt in)
   pytest -m docs                                   # strict docs build (opt in)

Layers
------

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Folder
     - What is asserted
   * - ``tests/core/``
     - Command parsing and dispatch; targets (a fake ``dronekit_sitl``); the GCS
       proxy over a real loopback UDP socket; the factory, including the Python
       version gate and a subprocess check that choosing ``dyopilot`` never
       imports ``dronekit``.
   * - ``tests/drivers/``
     - Flight logic against a fake MAVLink connection (``FakeMaster``): telemetry
       formatting, forward/back lat-lon math, takeoff ordering, rotate
       parameters, connect/close order and cleanup on failure, the reader thread.
       DroneKit logic against a fake ``Vehicle`` runs only in the Python 3.7
       environment.
   * - ``tests/gui/``
     - The session state machine and ordered command queue; the HTTP server on a
       real port: ``403`` without the token or with a foreign ``Host``/``Origin``,
       ``400``/``404``/``409``, and a full connect → command → disconnect cycle.
   * - ``tests/cli/``
     - Argument parsing and defaults per interpreter, controller wiring, shutdown
       on error and Ctrl-C, and that ``python -m dyodrone`` and the installed
       console scripts answer ``--help``.
   * - ``tests/integration/``
     - Opt-in (``-m sitl``): the real simulator. takeoff → land → close with no
       simulator process left, a standalone simulator driven as a Pixhawk target,
       and the web console flying it over HTTP.
   * - ``tests/test_docs_build.py``
     - Opt-in (``-m docs``): ``sphinx-build -W`` succeeds.

Regression tests worth knowing
------------------------------

``test_set_mode_sends_legacy_set_mode_message``
   Pins the ArduCopter 3.3 workaround: mode changes use ``SET_MODE`` and never
   ``MAV_CMD_DO_SET_MODE`` (:doc:`design_decisions`).
``test_dyopilot_never_imports_dronekit``
   Choosing the ``dyopilot`` driver must not import DroneKit, or the CLI breaks
   on Python 3.10+.
``test_failed_heartbeat_cleans_up_without_a_close_call``
   A failed ``connect()`` releases the target, so a half-started simulator is
   never left running.

Markers
-------

.. list-table::
   :header-rows: 1

   * - Marker
     - Meaning
   * - ``sitl``
     - Needs a live ArduCopter SITL; excluded by default.
   * - ``docs``
     - Builds the documentation; excluded by default.
   * - ``dronekit`` / ``dyopilot``
     - The test needs DroneKit (3.7 only) or pymavlink; skipped when not importable.

Test doubles
------------

``tests/fakes.py``: ``FakeController`` (records calls; can block or fail),
``FakeTarget`` (records acquire/release), ``FakeMaster``/``FakeMav`` (a MAVLink
connection with a message cache, flight mode and arming), and
``install_fake_dronekit_sitl``.
