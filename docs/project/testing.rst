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
       imports ``dronekit``. **Flight plans:** the parser (comments, ``wait``,
       line-numbered errors), the expectations (margin boundaries — 9 % passes, 11 %
       fails — floors, yaw wrap-around) and the closed-loop runner against a
       simulated vehicle on a fake clock (advances only on arrival, 3 s polling,
       timeout, command errors, pause/resume/stop). **Voice grammar:** number
       words, decimals, slicing of multi-command phrases, dropped incomplete ones.
   * - ``tests/drivers/``
     - Flight logic against a fake MAVLink connection (``FakeMaster``): telemetry
       formatting, forward/back lat-lon math, takeoff ordering, rotate
       parameters, connect/close order and cleanup on failure, the reader thread.
       DroneKit logic against a fake ``Vehicle`` runs only in the Python 3.7
       environment.
   * - ``tests/gui/``
     - The session state machine and ordered command queue; the runtime input
       switches, the plan lock and Land now; plan control and recording from the
       log; voice with a fake engine and manually fired timers (cancel window,
       ``land`` immediate, safety on disconnect/switch-off); the speech-engine
       adapter (model lookup, streaming download, Vosk wrapper with a fake module);
       the HTTP server on a real port: ``403`` without the token or with a foreign
       ``Host``/``Origin`` on every endpoint, ``400``/``404``/``409``, and a full
       connect → command → disconnect cycle.
   * - ``tests/cli/``
     - Argument parsing and defaults per interpreter, controller wiring, shutdown
       on error and Ctrl-C, and that ``python -m dyodrone`` and the installed
       console scripts answer ``--help``.
   * - ``tests/integration/``
     - Opt-in (``-m sitl``): the real simulator. takeoff → land → close with no
       simulator process left, a standalone simulator driven as a Pixhawk target,
       the web console flying it over HTTP, and ``dyodrone-plan`` flying a closed-loop
       plan (``takeoff 10, forward 15, right 90, land``) with both drivers.
       Opt-in (``-m voice``): macOS ``say`` synthesises speech that goes through the
       real Vosk model and the session's audio path.
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
``test_forward_north_is_done_within_ten_percent_of_the_distance``
   Pins the 10 % margin and the absolute floors of the flight-plan expectations.
``test_console_and_voice_are_locked_while_a_plan_runs`` / ``test_emergency_land_*``
   Pin the safety rules of the input switches.
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
   * - ``voice``
     - Needs ``vosk``, the model and macOS ``say``; excluded by default
       (``tox -e voice``).
   * - ``docs``
     - Builds the documentation; excluded by default.
   * - ``dronekit`` / ``dyopilot``
     - The test needs DroneKit (3.7 only) or pymavlink; skipped when not importable.

Test doubles
------------

``tests/fakes.py``: ``FlyingController`` (a controller with simple flight dynamics
whose telemetry moves toward commanded goals, so plans run closed-loop) with
``FakeClock``; ``FakeEngine`` and ``FakeTimer`` for voice; ``FakeController`` (records calls; can block or fail),
``FakeTarget`` (records acquire/release), ``FakeMaster``/``FakeMav`` (a MAVLink
connection with a message cache, flight mode and arming), and
``install_fake_dronekit_sitl``.
