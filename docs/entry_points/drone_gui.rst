drone_gui.py
============

A browser-based console for the same vehicle commands as :doc:`drone_cli`. It
shows live vehicle info, takes commands at a prompt, and lets you switch
between the simulator and a real Pixhawk and connect or disconnect — without a
terminal UI. It uses only the standard library, so it runs on both the Python
3.7 and the Python 3.12 environments.

.. code-block:: bash

   python entry_points/drone_gui.py [--host HOST] [--port PORT]
                                    [--family {dronekit,dyopilot}] [--no-browser]

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
   * - ``--family``
     - by interpreter
     - ``dronekit`` or ``dyopilot``. Defaults to ``dronekit`` on Python < 3.10
       and ``dyopilot`` otherwise.
   * - ``--no-browser``
     - off
     - Print the URL instead of opening a browser.

Which backend family you get
----------------------------

Like the CLI, one process runs on one interpreter, and DroneKit and dyopilot
need different ones. The header badge shows the active family and Python
version (for example ``dyopilot · Python 3.12.14``). To use the other family,
start the GUI from the other environment — see :doc:`../guide/installation`.
Choosing ``--family dronekit`` on Python 3.10+ is allowed but the connection
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

Connection toggle
-----------------

.. list-table::
   :header-rows: 1
   :widths: 18 42 40

   * - Toggle
     - Connects to
     - Extra field
   * - **Simulator**
     - ``<family>-sitl``: starts the built-in ArduCopter 3.3 simulator
     - *QGC UDP port* (default 14550; ``0`` disables the proxy)
   * - **Pixhawk**
     - ``<family>-pixhawk``: the board at the connection string
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
* anything else is answered with ``403``.

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
     - Status, mode, telemetry lines, connection details and log entries with
       id greater than ``N``.
   * - ``POST /api/connect``
     - ``{"mode": "sitl"|"pixhawk", "connection": "…", "gcs_port": 14550}``.
       Returns at once; poll the state. ``409`` if already connecting or
       connected.
   * - ``POST /api/disconnect``
     - Close the connection (``409`` while a connection attempt is running).
   * - ``POST /api/command``
     - ``{"line": "takeoff 10"}``. Queued; results appear in the log.

Code lives in ``drone_gui/`` (:doc:`../api/gui`); the command and backend logic
is shared with the CLI in ``drone_console.py`` (:doc:`../api/console`).
