History
=======

Newest first. Dates are commit dates from ``git log``.

Unreleased
----------

*Working tree on top of* ``48f2ccf``.

* **Flight plans.** Plain-text plans (one console command per line, ``#`` comments,
  optional ``wait``) run closed-loop: each step is verified from MAVLink telemetry
  every 3 s against its expected end state (10 % margin) before the next starts.
  ``dyodrone-plan`` runs them with no UI; the web console has a plan panel,
  recording from the session log, upload and download.
* **Voice.** Offline speech recognition (Vosk, optional ``voice`` extra) sliced into
  commands with exactly the console keywords; recognised commands wait a cancellable
  2 s, ``land`` runs at once.
* **Runtime input switches.** Console / Plan / Voice can be turned on and off while
  the web console runs; plans lock the other inputs; **Land now** overrides everything.
* **Telemetry.** ``DroneController.telemetry()`` for both drivers.
* **Package.** Code moved into ``src/dyodrone`` and is installed with
  ``pip install -e ".[dronekit]"`` or ``".[dyopilot]"``. ``dyodrone-cli``,
  ``dyodrone-gui`` and ``python -m dyodrone`` replace the ``entry_points/``
  scripts; requirements files became extras.
* **Driver × target.** ``--backend`` is replaced by ``--driver {dronekit,dyopilot}``
  and ``--target {sitl,pixhawk}``. Two controllers (``DroneKitController``,
  ``DyopilotController``) take a ``Target`` (``SitlTarget`` / ``ExternalTarget``);
  the four ``*SITL`` / ``*Pixhawk`` subclasses are gone. The QGC proxy works with
  either target.
* **dyopilot driver** on raw pymavlink with a background ``MAVLinkReader``, runs
  on Python 3.12+; ``dyopilot-pixhawk`` is new.
* **Web console** ``dyodrone-gui``: a browser GUI with a console prompt, live
  vehicle info, a Simulator/Pixhawk toggle and Connect/Disconnect. Standard
  library only; runs on Python 3.7 and 3.12.
* **Tests.** A layered pytest suite (core, drivers, GUI, CLI) plus opt-in
  live-simulator and docs-build tests; tox environments for Python 3.12 and 3.7.
* **Fix:** mode changes on the bundled ArduCopter 3.3 use the legacy ``SET_MODE``
  message (:doc:`design_decisions`).
* **Fix:** a failed ``connect()`` releases the target, so no simulator is left
  running.
* **CLI:** lazy driver imports and a Python-version gate for ``dronekit``.
* **Documentation** rebuilt as a Sphinx project with the Furo theme (guide, entry
  points, API reference, project notes).

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
