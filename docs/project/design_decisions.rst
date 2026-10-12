Design decisions
================

Short records of why the code is shaped the way it is. Each lists the
decision, the reason, and where it shows up.

Two virtual environments instead of one
---------------------------------------

*Decision.* The ``dronekit`` driver runs on Python 3.7; the ``dyopilot``
driver runs on 3.12+. They never share an interpreter.

*Why.* ``dronekit==2.9.2`` subclasses ``collections.MutableMapping``
(removed in Python 3.10), so ``import dronekit`` cannot work on a current
interpreter. dyopilot exists to avoid that dependency.

*Where.* :doc:`../guide/installation`, the ``dronekit`` and ``dyopilot`` extras in ``pyproject.toml``.

``dronekit_sitl`` runs in-process on Python 3.12
------------------------------------------------

*Decision.* ``SitlTarget`` calls ``dronekit_sitl.start_default()`` directly,
in-process, for either driver;
there is no helper process running under Python 3.7.

*Why.* Checked empirically in a throwaway Python 3.12 environment:
``dronekit_sitl``'s runtime code never imports ``dronekit`` (only its unused
``forwarder.py`` does), and ``start_default()`` boots a working simulator.
A cross-interpreter subprocess bridge would have added a launch protocol,
interpreter discovery and orphan-process handling for no benefit.

*Where.* ``dyodrone/core/targets.py`` (``SitlTarget``).

Lazy driver imports plus a version gate
---------------------------------------------------

*Decision.* ``create_controller()`` imports a driver only inside the branch
that selects it, and the ``dronekit`` driver raises ``BackendUnavailable`` with
an explanatory message on Python ≥ 3.10 (the CLI turns it into an exit
message, the web console into a red console line).

*Why.* Importing all controllers at the top of the file meant a single
``from dronekit import …`` broke the whole CLI on new Pythons, even for
drivers that never use DroneKit.

*Where.* ``dyodrone/core/factory.py`` (``create_controller``, ``require_python37``).

Legacy ``SET_MODE`` instead of ``set_mode_apm()``
-------------------------------------------------

*Decision.* ``DyopilotController._set_mode`` sends ``SET_MODE`` via
``mav.set_mode_send`` using ``master.mode_mapping()``.

*Why.* pymavlink 2.4.8 sent ``SET_MODE``; current releases send
``MAV_CMD_DO_SET_MODE`` in a ``COMMAND_LONG``. The bundled ArduCopter 3.3
answers that with ``COMMAND_ACK`` result 3 (unsupported), so the mode never
changed and ``takeoff`` timed out. Found by running a live simulator, not by
reading code.

*Where.* ``dyodrone/drivers/dyopilot_driver.py``; pinned by a regression test.

One GCS proxy shared by both drivers
---------------------------------------------

*Decision.* ``GCSProxy`` has two entry points: ``start(vehicle)`` for
DroneKit's message listener and ``forward(raw_bytes)`` for anything else. The
The dyopilot driver passes ``proxy.forward`` as the ``on_frame`` callback of
``MAVLinkReader``.

*Why.* The simulator streams to one TCP client only, so the proxy forwards
frames the driver already receives over UDP rather than opening a second
connection.

*Where.* ``dyodrone/core/proxy.py``, ``dyodrone/drivers/dyopilot_reader.py``.

A reader thread for pymavlink
-----------------------------

*Decision.* ``MAVLinkReader`` drains the connection on a daemon thread.

*Why.* Unlike DroneKit, pymavlink has no listener dispatch: nothing fills
``master.messages`` / ``master.flightmode`` unless something keeps calling
``recv_msg()``.

*Where.* ``dyodrone/drivers/dyopilot_reader.py``.

Driver and target are separate
------------------------------

*Decision.* A controller is *driver × target*: ``DroneKitController(target)`` and
``DyopilotController(target)``, where a ``Target`` (``SitlTarget`` or
``ExternalTarget``) supplies the connection string and tears down what it
started. The four ``*SITL`` / ``*Pixhawk`` subclasses were removed, and
``--backend`` became ``--driver`` and ``--target``.

*Why.* The four "backends" were really two independent choices: the library
decides the Python environment, the target only decides where the connection
string comes from. Four classes duplicated the same start-simulator-or-use-a-string
logic per library, and front ends had to build and re-parse ``"<family>-<mode>"``
strings. As a side effect the QGC proxy now works with either target.

*Where.* ``dyodrone/core/targets.py``, ``dyodrone/drivers/``, ``dyodrone/core/factory.py``.

One installable package with console scripts
--------------------------------------------

*Decision.* Code lives in ``src/dyodrone`` and is installed with
``pip install -e ".[<extra>]"``; ``dyodrone-cli`` and ``dyodrone-gui`` are console
scripts (plus ``python -m dyodrone``). Dependencies are extras
(``dronekit``, ``dyopilot``, ``docs``, ``test``) instead of requirements files.

*Why.* A script in an ``entry_points/`` folder had to patch ``sys.path`` to find
the code beside it, and three requirements files lived in three folders. With a
package, imports are ordinary, entry points are on ``PATH`` after installing, and
one file says what each environment needs. The package stays Python 3.7
compatible so the same project installs in both environments.

*Where.* ``pyproject.toml``.

tox as the runner
-----------------

*Decision.* ``tox.ini`` has one environment per task (``dyopilot`` on 3.12,
``dronekit`` on 3.7, ``sitl``, ``docs``) in place of ``build_docs.sh``.

*Why.* The recurring question is "which Python and which extras for this task";
tox writes the answer down and creates the environments. The Python 3.7
environments pin the pip and setuptools virtualenv seeds, because the defaults no
longer run on 3.7.

*Where.* ``tox.ini``; :doc:`../entry_points/runners`.

Command handling and driver selection live in the core
------------------------------------------------------

*Decision.* ``handle_command()`` and ``create_controller()`` live in
``dyodrone.core``, which imports no UI toolkit, and both front ends use them.

*Why.* The curses CLI and the web console must behave identically; copying the
command parser would let them drift. The unusable-driver case is an exception
(``BackendUnavailable``) rather than ``SystemExit`` because a worker thread
silently swallows ``SystemExit``.

*Where.* ``dyodrone/core/commands.py``, ``dyodrone/core/factory.py``.

DroneKit is mocked when building the docs
-----------------------------------------

*Decision.* ``autodoc_mock_imports = ['dronekit', 'dronekit_sitl']``;
``pymavlink`` is installed for real.

*Why.* DroneKit cannot be imported on the docs interpreter. ``pymavlink`` is
needed because the dyopilot driver ORs ``mavutil`` constants at import time,
which a mock cannot do.

*Where.* ``docs/conf.py``.

A local web page instead of a desktop toolkit
---------------------------------------------

*Decision.* The GUI is a browser page served by ``http.server`` from the
standard library, not tkinter or Qt.

*Why.* Checked on the development machine: ``tkinter`` was available only in
the Python 3.7 interpreter; the 3.12 environments had no ``_tkinter``. Qt would
add a large dependency and not support 3.7. A stdlib server and a single HTML
file run unchanged in both environments, so both drivers get a GUI.

*Where.* ``dyodrone/gui/``.

Token, Host and Origin checks on the GUI API
--------------------------------------------

*Decision.* Every ``/api/*`` call needs a random per-run token, a ``Host``
matching the bound address and, if present, a matching ``Origin``.

*Why.* The endpoints command a vehicle. Without these checks any other page
open in the browser could POST to ``localhost`` (cross-site request forgery) or
use DNS rebinding to reach the server.

*Where.* ``dyodrone/gui/server.py``.

A command worker thread with polling
------------------------------------

*Decision.* Connecting, ``takeoff`` and disconnecting run on background
threads; commands share one ordered queue; the page polls ``/api/state`` every
second.

*Why.* Booting a simulator takes tens of seconds and ``takeoff`` blocks until
the vehicle is armed, so requests must return immediately. A single queue keeps
commands in order. Polling avoids websockets, which the standard library does
not provide.

*Where.* ``dyodrone/gui/session.py``.
