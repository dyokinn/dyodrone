Troubleshooting
===============

Problems that have actually been hit while building this project, with their
cause and fix. QGroundControl-specific problems are in :doc:`proxy`.

``Backend 'dronekit-…' requires Python 3.7``
--------------------------------------------

You ran a ``dronekit-*`` backend on Python 3.10+. The CLI refuses up front
instead of crashing. Activate the Python 3.7 environment
(:doc:`installation`), or switch to the equivalent ``dyopilot-*`` backend.

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
itself (``_PyMAVLinkBase._set_mode``). If you write new pymavlink code against
this simulator, do the same. Details: :doc:`../project/design_decisions`.

"No heartbeat received" when connecting a second client
-------------------------------------------------------

The SITL instance streams to a single TCP client. A second
``mavlink_connection('tcp:127.0.0.1:5760')`` while a backend is running gets no
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

Autodoc imports the project. Use ``./entry_points/build_docs.sh`` (it installs
``pymavlink`` and mocks DroneKit). A raw ``sphinx-build`` in an environment
without ``pymavlink`` fails when importing ``dyopilot_version``.
