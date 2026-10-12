Design decisions
================

Short records of why the code is shaped the way it is. Each lists the
decision, the reason, and where it shows up.

Two virtual environments instead of one
---------------------------------------

*Decision.* DroneKit backends run on Python 3.7; dyopilot backends run on
3.12+. They never share an interpreter.

*Why.* ``dronekit==2.9.2`` subclasses ``collections.MutableMapping``
(removed in Python 3.10), so ``import dronekit`` cannot work on a current
interpreter. dyopilot exists to avoid that dependency.

*Where.* :doc:`../guide/installation`, the two requirements files.

``dronekit_sitl`` runs in-process on Python 3.12
------------------------------------------------

*Decision.* ``dyopilot-sitl`` calls ``dronekit_sitl.start_default()`` directly;
there is no helper process running under Python 3.7.

*Why.* Checked empirically in a throwaway Python 3.12 environment:
``dronekit_sitl``'s runtime code never imports ``dronekit`` (only its unused
``forwarder.py`` does), and ``start_default()`` boots a working simulator.
A cross-interpreter subprocess bridge would have added a launch protocol,
interpreter discovery and orphan-process handling for no benefit.

*Where.* ``dyopilot_version/dyopilot_sitl_controller.py``.

Lazy backend imports plus a version gate in the CLI
---------------------------------------------------

*Decision.* ``create_controller()`` imports a backend only inside the branch
that selects it, and ``dronekit-*`` backends raise ``BackendUnavailable`` with
an explanatory message on Python ≥ 3.10 (the CLI turns it into an exit
message, the web console into a red console line).

*Why.* Importing all controllers at the top of the file meant a single
``from dronekit import …`` broke the whole CLI on new Pythons, even for
backends that never use DroneKit.

*Where.* ``drone_console.py`` (``create_controller``, ``require_python37``).

Legacy ``SET_MODE`` instead of ``set_mode_apm()``
-------------------------------------------------

*Decision.* ``_PyMAVLinkBase._set_mode`` sends ``SET_MODE`` via
``mav.set_mode_send`` using ``master.mode_mapping()``.

*Why.* pymavlink 2.4.8 sent ``SET_MODE``; current releases send
``MAV_CMD_DO_SET_MODE`` in a ``COMMAND_LONG``. The bundled ArduCopter 3.3
answers that with ``COMMAND_ACK`` result 3 (unsupported), so the mode never
changed and ``takeoff`` timed out. Found by running a live simulator, not by
reading code.

*Where.* ``dyopilot_version/dyopilot_controller.py``.

One GCS proxy shared by both backend families
---------------------------------------------

*Decision.* ``GCSProxy`` has two entry points: ``start(vehicle)`` for
DroneKit's message listener and ``forward(raw_bytes)`` for anything else. The
dyopilot backends pass ``proxy.forward`` as the ``on_frame`` callback of
``MAVLinkReader``.

*Why.* The simulator streams to one TCP client only, so the proxy forwards
frames the backend already receives over UDP rather than opening a second
connection.

*Where.* ``dronekit_version/gcs_proxy.py``, ``dyopilot_version/pymavlink_reader.py``.

A reader thread for pymavlink
-----------------------------

*Decision.* ``MAVLinkReader`` drains the connection on a daemon thread.

*Why.* Unlike DroneKit, pymavlink has no listener dispatch: nothing fills
``master.messages`` / ``master.flightmode`` unless something keeps calling
``recv_msg()``.

*Where.* ``dyopilot_version/pymavlink_reader.py``.

Entry points in their own folder
--------------------------------

*Decision.* Everything you run lives in ``entry_points/``; library code stays
at the repo root.

*Why.* Keeps runnable files separate from importable ones. Because the script
now lives one level below the packages, it puts the repo root on ``sys.path``
itself.

*Where.* :doc:`../entry_points/index`.

DroneKit is mocked when building the docs
-----------------------------------------

*Decision.* ``autodoc_mock_imports = ['dronekit', 'dronekit_sitl']``;
``pymavlink`` is installed for real.

*Why.* DroneKit cannot be imported on the docs interpreter. ``pymavlink`` is
needed because ``dyopilot_version`` ORs ``mavutil`` constants at import time,
which a mock cannot do.

*Where.* ``docs/conf.py``.

Front-end logic lives in one shared module
------------------------------------------

*Decision.* ``handle_command()``, ``create_controller()`` and the backend
tables were moved out of ``entry_points/drone_cli.py`` into ``drone_console.py``,
which imports no UI toolkit.

*Why.* The curses CLI and the web console must behave identically; copying the
command parser would let them drift. The unusable-backend case became an
exception (``BackendUnavailable``) rather than ``SystemExit`` because a worker
thread silently swallows ``SystemExit``.

*Where.* ``drone_console.py``.

A local web page instead of a desktop toolkit
---------------------------------------------

*Decision.* The GUI is a browser page served by ``http.server`` from the
standard library, not tkinter or Qt.

*Why.* Checked on the development machine: ``tkinter`` was available only in
the Python 3.7 interpreter; the 3.12 environments had no ``_tkinter``. Qt would
add a large dependency and not support 3.7. A stdlib server and a single HTML
file run unchanged in both environments, so both backend families get a GUI.

*Where.* ``drone_gui/``, ``entry_points/drone_gui.py``.

Token, Host and Origin checks on the GUI API
--------------------------------------------

*Decision.* Every ``/api/*`` call needs a random per-run token, a ``Host``
matching the bound address and, if present, a matching ``Origin``.

*Why.* The endpoints command a vehicle. Without these checks any other page
open in the browser could POST to ``localhost`` (cross-site request forgery) or
use DNS rebinding to reach the server.

*Where.* ``drone_gui/server.py``.

A command worker thread with polling
------------------------------------

*Decision.* Connecting, ``takeoff`` and disconnecting run on background
threads; commands share one ordered queue; the page polls ``/api/state`` every
second.

*Why.* Booting a simulator takes tens of seconds and ``takeoff`` blocks until
the vehicle is armed, so requests must return immediately. A single queue keeps
commands in order. Polling avoids websockets, which the standard library does
not provide.

*Where.* ``drone_gui/session.py``.
