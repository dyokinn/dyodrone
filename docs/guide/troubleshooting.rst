Troubleshooting
===============

Problems that have actually been hit while building this project, with their
cause and fix. QGroundControl-specific problems are in :doc:`proxy`.

``Driver 'dronekit' requires Python 3.7``
--------------------------------------------

You ran ``--driver dronekit`` on Python 3.10+. The CLI refuses up front
instead of crashing. Activate the Python 3.7 environment
(:doc:`installation`), or use ``--driver dyopilot``.

``AttributeError: module 'collections' has no attribute 'MutableMapping'``
--------------------------------------------------------------------------

``import dronekit`` on Python 3.10+. DroneKit 2.9.2 subclasses
``collections.MutableMapping``, which was removed in 3.10. On a bare 3.12
install you may instead see ``ModuleNotFoundError: No module named 'past'``
(DroneKit also needs the ``future`` package). Both mean the same thing: use
Python 3.7 for DroneKit. ``dronekit_sitl`` alone *does* work on 3.12.

``pymavlink==2.4.8`` fails to build on Python 3.12
--------------------------------------------------

``AttributeError: 'array.array' object has no attribute 'fromstring'`` during
``pip install``. That pin belongs to the 3.7 environment only; the dyopilot
environment pins ``pymavlink==2.4.49``.

``takeoff`` times out with "Failed to enter GUIDED mode"
--------------------------------------------------------

Cause: current pymavlink's ``set_mode_apm()`` sends ``MAV_CMD_DO_SET_MODE``,
which the bundled ArduCopter 3.3 firmware rejects (``COMMAND_ACK`` result 3,
"unsupported"). dyopilot therefore sends the legacy ``SET_MODE`` message
itself (``DyopilotController._set_mode``). If you write new pymavlink code against
this simulator, do the same. Details: :doc:`../project/design_decisions`.

"No heartbeat received" when connecting a second client
-------------------------------------------------------

The SITL instance streams to a single TCP client. A second
``mavlink_connection('tcp:127.0.0.1:5760')`` while a driver is connected gets no
heartbeat and times out. To watch the same simulator from another tool, use the
UDP GCS proxy (``--gcs-port``), not a second TCP connection.

Telemetry shows ``unknown`` right after start
---------------------------------------------

Normal. Fields fill in as MAVLink messages arrive; GPS-dependent values take
about 6–10 seconds after boot. ``takeoff`` itself waits for a 3D fix (up to
60 s) before arming.

The console looks broken or exits immediately
---------------------------------------------

The CLI uses ``curses`` and needs a real terminal (not a piped or non-interactive
shell). Resize the window if lines are cut off; each line is truncated to the
terminal width.

Docs build fails on import errors
---------------------------------

Autodoc imports the project. Use ``tox -e docs`` (it installs the ``docs`` extra, including
``pymavlink``, and the build mocks DroneKit). A raw ``sphinx-build`` in an
environment without the package or ``pymavlink`` fails when importing
``dyodrone.drivers``.

Web console
-----------

"invalid token — reopen the URL printed in the terminal"
   The page was opened without the per-run token, or the server was restarted
   (each start has a new token). Use the URL ``dyodrone-gui`` printed.

"server unreachable"
   The ``dyodrone-gui`` process stopped. Start it again.

``Cannot listen on 127.0.0.1:8765``
   The port is taken, often by an earlier run. Pick another with ``--port``
   (``0`` chooses a free one).

Nothing opens in the browser
   Use ``--no-browser`` and open the printed URL yourself.

Connect fails immediately with "requires Python 3.7"
   The ``dronekit`` driver was selected on Python 3.10+. Start the GUI from the
   Python 3.7 environment, or leave ``--driver`` at its default.

``takeoff`` seems stuck
   It blocks until the vehicle is armable, in GUIDED mode and armed (up to a
   minute or so). The console shows ``running: takeoff …``; other commands wait
   in the queue, except ``info`` and ``help``.

Flight plans
------------

``line N: …`` when validating
   The plan text has a problem on that line; every problem is listed at once.
   See :doc:`plans` for the format.

A step ``timed out after 120 s``
   The vehicle did not reach the expected state in time. The message shows the last
   measured values (for example ``alt 4.1/10 m (±1.0)``). Common causes: a command the
   vehicle ignored (not armed, wrong mode), a very long move (raise
   ``--step-timeout``), or no GPS position yet. The plan stops there and the vehicle
   hovers; use ``land`` or **Land now**.

A short move never "finishes"
   The margin has a floor (0.5 m, 2°) so tiny moves are achievable, but real GPS noise
   can exceed it. Raise ``--margin`` or the floors, or use longer moves.

"waiting for position telemetry"
   The plan needs a position and heading before it can compute where a ``forward`` or
   ``back`` should end. Wait for a 3D GPS fix (about 10 s after the simulator starts).

Console and voice commands are refused while a plan runs
   By design: they would invalidate the plan's expected positions. **Stop** the plan
   (the vehicle hovers) or use **Land now**.

Voice
-----

"Voice input unavailable: … vosk"
   Install the optional package: ``pip install "dyodrone[voice]"`` in the same
   environment as ``dyodrone-gui``.

"Could not download the speech model"
   The first use downloads about 40 MB. Download
   ``vosk-model-small-en-us-0.15.zip`` yourself, unzip it, and start with
   ``dyodrone-gui --vosk-model /path/to/vosk-model-small-en-us-0.15``.

"Microphone unavailable …"
   The browser refused microphone access. Allow it for the page and switch Voice on
   again. The page must be served from ``127.0.0.1`` or ``localhost`` (or https);
   a console bound to another address cannot use the microphone.

Commands are not recognised, or are mis-heard
   Say the keywords exactly (``takeoff``, not ``take off``), speak numbers as words
   (``twenty five``), and pause briefly between commands so the phrase ends. The
   console shows ``heard: "…"`` for every phrase and a note for anything dropped.
   The small model is limited to the console vocabulary on purpose.

A voice command did not run
   Recognised commands wait ``--voice-delay`` seconds (default 2) so you can cancel
   them, and are refused if the Voice switch was turned off or a plan started in
   the meantime (the console says so). ``land`` is never delayed.
