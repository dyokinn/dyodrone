History
=======

Newest first. Dates are commit dates from ``git log``.

Unreleased
----------

*Working tree on top of* ``48f2ccf``.

* **Four backends.** ``--backend`` is now ``dronekit-sitl``,
  ``dronekit-pixhawk``, ``dyopilot-sitl`` or ``dyopilot-pixhawk`` (previously
  ``sitl``, ``pixhawk``, ``mavlink``).
* **dyopilot split** into ``_PyMAVLinkBase``, ``DyopilotSITLController`` and
  ``DyopilotPixhawkController`` with a background ``MAVLinkReader``;
  ``dyopilot.py`` removed. ``dyopilot-pixhawk`` is new.
* **Separate requirements** for the 3.12 environment
  (``dyopilot_version/requirements.txt``).
* **Fix:** mode changes on the bundled ArduCopter 3.3 now use the legacy
  ``SET_MODE`` message (:doc:`design_decisions`).
* **CLI:** lazy backend imports and a Python-version gate for ``dronekit-*``.
* **GCSProxy.forward()** added so non-DroneKit backends can feed the proxy.
* **Web console** ``entry_points/drone_gui.py``: a browser GUI with a console
  prompt, live vehicle info, a Simulator/Pixhawk toggle and Connect/Disconnect.
  Standard library only; runs on Python 3.7 and 3.12.
* **Shared module** ``drone_console.py``: ``create_controller()`` and
  ``handle_command()`` moved out of the CLI so both front ends share them.
* **Entry points** moved to ``entry_points/``; ``drone_cli.py`` bootstraps
  ``sys.path``.
* **Documentation** rebuilt as a Sphinx project with the Furo theme
  (guide, entry points, API reference, project notes) and a ``build_docs.sh``
  script.

2026-03-21 — ``48f2ccf`` "FEAT: FIRST STABLE VERSION"
-----------------------------------------------------

* ``drone_sim_cli.py`` renamed to ``drone_cli.py``.
* Introduced the abstract ``DroneController`` (``drone_controller.py``).
* DroneKit logic split into ``_DroneKitBase``, ``DronekitSITLController`` and
  ``DronekitPixhawkController``.
* Added ``GCSProxy`` for QGroundControl telemetry over UDP.
* Added the first documentation (architecture, how it works, proxy) and a
  placeholder ``dyopilot.py`` backend.

2026-02-28 — ``8bdcb0e`` "feat: added NSWE for SITL"
----------------------------------------------------

* First CLI (``drone_sim_cli.py``) and DroneKit controller.
* Added ``dronekit_version/requirements-3.7.17.txt``.
* Empty ``dyopilot_version/dyopilot.py`` reserved for the future backend.
