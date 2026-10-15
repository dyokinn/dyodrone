dyodrone-gui
============

A browser-based console for the same vehicle commands as :doc:`dyodrone_cli`. It
shows live vehicle info, lets you switch between the simulator and a real
Pixhawk, and accepts commands from **three input types that you can switch on
and off while it runs**: the console prompt, a :doc:`flight plan
<../guide/plans>`, and :doc:`voice <../guide/voice>`. The server uses only the
standard library, so it runs on both the Python 3.7 and the Python 3.12
environments (voice needs the optional ``voice`` extra).

.. code-block:: bash

   dyodrone-gui [--host HOST] [--port PORT] [--driver {dronekit,dyopilot}] [--no-browser]
                [--plan-poll S] [--plan-margin F] [--plan-timeout S]
                [--voice-delay S] [--vosk-model FOLDER]

The script prints a URL such as ``http://127.0.0.1:8765/?token=…`` and opens it
in your browser. Press ``Ctrl+C`` (or send ``SIGTERM``) to stop it; the vehicle
connection, QGroundControl proxy and any simulator are closed on the way out.

Arguments
---------

.. list-table::
   :header-rows: 1
   :widths: 20 24 56

   * - Argument
     - Default
     - Meaning
   * - ``--host``
     - ``127.0.0.1``
     - Address to bind. Keep it on loopback unless you understand the
       :ref:`security note <gui-security>` below.
   * - ``--port``
     - ``8765``
     - Port to serve on; ``0`` picks any free port.
   * - ``--driver``
     - by interpreter
     - ``dronekit`` or ``dyopilot``. Defaults to ``dronekit`` on Python < 3.10
       and ``dyopilot`` otherwise.
   * - ``--plan-poll``
     - ``3``
     - Flight plans: seconds between telemetry checks while a command runs.
   * - ``--plan-margin``
     - ``0.10``
     - Flight plans: allowed error as a fraction of the commanded amount.
   * - ``--plan-timeout``
     - ``120``
     - Flight plans: fail a step not completed this long after it was sent.
   * - ``--voice-delay``
     - ``2``
     - Voice: seconds a recognised command waits, cancellable, before it runs.
   * - ``--vosk-model``
     - (download once)
     - Voice: folder of an unpacked Vosk model.
   * - ``--no-browser``
     - off
     - Print the URL instead of opening a browser.

Which driver you get
----------------------------

Like the CLI, one process runs on one interpreter, and DroneKit and dyopilot
need different ones. The header badge shows the active driver and Python
version (for example ``dyopilot · Python 3.12.14``). To use the other driver,
start the GUI from the other environment — see :doc:`../guide/installation`.
Choosing ``--driver dronekit`` on Python 3.10+ is allowed but the connection
fails with the usual "requires Python 3.7" message in the console.

The page
--------

Header
   Family and Python badge, a status indicator (``disconnected``,
   ``connecting``, ``connected``, ``disconnecting``, ``error``), the connection
   controls and a Connect/Disconnect button.

Console
   Scrollback of everything that happened — your commands, their results
   (errors in red), and connection events — with a prompt. ``↑``/``↓`` recall
   earlier commands, ``Ctrl-L`` or ``clear`` clears the screen, and the buttons
   under the prompt fill it with a command (press Enter to send, so nothing
   flies by accident).

Vehicle and Connection panels
   The same snapshot the CLI shows, refreshed every second, plus the connection
   string and QGroundControl proxy target.

Input switches
--------------

Three switches under the header turn input types on and off **at runtime**,
without reconnecting:

.. list-table::
   :header-rows: 1
   :widths: 14 14 72

   * - Switch
     - Default
     - Effect
   * - **Console**
     - on
     - The prompt and the command buttons accept input. Off: the prompt is disabled
       and the server refuses console commands.
   * - **Plan**
     - off
     - Enables the Flight plan panel (:doc:`../guide/plans`). Turning it off stops a
       running plan.
   * - **Voice**
     - off
     - Starts listening on the microphone (:doc:`../guide/voice`). The first time,
       the speech model is loaded (and downloaded once). Turning it off closes the
       microphone and drops pending voice commands.

The switches are independent, and their state is on the server, so it survives a
page reload. Rules that keep them from fighting each other:

* While a **flight plan runs**, console and voice commands are locked out (they would
  invalidate the plan's expected positions). The prompt shows "Locked while a flight
  plan runs".
* **Land now** (red button, top right) is always available while connected. It
  ignores every switch and lock: it stops the plan, drops queued and pending
  voice commands, and lands at once.
* A switch that is off refuses commands from its source with a message instead
  of silently ignoring them.

Flight-plan panel
-----------------

*Upload .txt* / the editor / *From log* / *Download* / *Validate*, then **Run**,
**Pause**/**Resume** and **Stop**. The step list shows each step's state
(``○`` pending, ``◔`` waiting for the vehicle, ``✓`` done, ``✗`` failed) with the
latest measured-versus-expected values, for example ``alt 8.5/10 m (±1.0)``.
Errors are listed with their line numbers. *From log* loads the flight commands you
ran successfully this session. Format and behaviour: :doc:`../guide/plans`.

Voice panel
-----------

Shows whether the microphone is listening, the live partial transcript, and the
**pending voice commands** with a countdown and a **Cancel** button each (plus
**Cancel all**). Details: :doc:`../guide/voice`. The page needs microphone
permission; if the browser refuses, Voice switches itself off and the panel says why.

Connection toggle
-----------------

.. list-table::
   :header-rows: 1
   :widths: 18 42 40

   * - Toggle
     - Connects to
     - Extra field
   * - **Simulator**
     - ``--target sitl``: starts the built-in ArduCopter 3.3 simulator
     - *QGC UDP port* (default 14550; ``0`` disables the proxy)
   * - **Pixhawk**
     - ``--target pixhawk``: the board at the connection string
     - *Connection*, e.g. ``tcp:127.0.0.1:5760`` or ``/dev/ttyUSB0``

The toggle and fields lock while connecting or connected; press **Disconnect**
to change them. After a failed connection the status shows ``error`` and you
can adjust the fields and connect again.

Console commands
----------------

Everything the CLI accepts — ``takeoff <alt>``, ``altitude <alt>``,
``forward <m>``, ``back <m>``, ``left <deg>``, ``right <deg>``, ``land`` — plus:

``help``
   List the commands.
``info``
   Print the vehicle snapshot and connection details into the console.
``quit`` / ``exit``
   Disconnect (the page and server stay up).
``clear``
   Clear the screen.

Commands run one at a time, in order, on a worker thread, so a long ``takeoff``
never freezes the page. While one runs, the console shows ``running: …`` and how
many are queued. ``info`` and ``help`` answer immediately.

.. _gui-security:

Security
--------

These requests can fly a vehicle, so the server defends against other web pages
in your browser trying to reach ``localhost``:

* every ``/api/*`` request must carry the random per-run token from the printed
  URL (the page keeps it in ``sessionStorage`` and removes it from the address
  bar);
* the ``Host`` header must match the address the server is bound to, and an
  ``Origin`` header, if present, must be the server itself;
* anything else is answered with ``403``. This applies to every endpoint,
  including the microphone audio upload.

The default bind address is loopback only. If you bind another address with
``--host``, anyone who can reach it *and* knows the token can command the
vehicle, and traffic is not encrypted.

HTTP API
--------

Used by the page; documented for scripting. All calls need the ``X-Token``
header.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Request
     - Effect
   * - ``GET /api/state?since=N``
     - Status, driver, target, telemetry lines, connection details and log entries with
       id greater than ``N``.
   * - ``POST /api/connect``
     - ``{"target": "sitl"|"pixhawk", "connection": "…", "gcs_port": 14550}``.
       Returns at once; poll the state. ``409`` if already connecting or
       connected.
   * - ``POST /api/disconnect``
     - Close the connection (``409`` while a connection attempt is running).
   * - ``POST /api/command``
     - ``{"line": "takeoff 10"}``. Queued; results appear in the log. ``409`` if
       the Console switch is off or a plan is running.
   * - ``POST /api/inputs``
     - ``{"console": true, "plan": false, "voice": true}`` — any subset; state
       reports ``inputs``. ``400`` for unknown names or non-booleans.
   * - ``POST /api/emergency``
     - Land now (``409`` if not connected).
   * - ``POST /api/plan``
     - ``{"text": "…"}`` validates and loads a plan; ``200`` with the steps, or
       ``400`` with ``errors: [{"line", "message"}]``.
   * - ``POST /api/plan/run``, ``/pause``, ``/resume``, ``/stop``
     - Control the loaded plan (``409`` if the Plan switch is off, nothing is
       loaded, or the state does not allow it). Progress is in ``state.plan``.
   * - ``GET /api/plan/history``
     - ``{"text", "count"}``: the session's successful flight commands as plan text.
   * - ``POST /api/voice/audio``
     - Raw 16 kHz mono little-endian PCM16 body (≤ 128 KB). Returns the live
       partial transcript. ``409`` if Voice is off or still loading.
   * - ``POST /api/voice/cancel``
     - ``{"id": n}`` cancels one pending voice command, ``{}`` all of them.

Code lives in ``dyodrone.gui`` (:doc:`../api/gui`); the command and driver logic
is shared with the CLI in ``dyodrone.core`` (:doc:`../api/core`).
