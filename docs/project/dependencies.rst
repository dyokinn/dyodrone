Dependencies
============

Dependencies are declared in ``pyproject.toml`` as **extras** — one per
environment — and each environment is its own virtual environment. Nothing is
shared at runtime. The core package itself has no dependencies.

DroneKit environment — Python 3.7
---------------------------------

``pip install -e ".[dronekit]"``

.. list-table::
   :header-rows: 1
   :widths: 24 12 64

   * - Package
     - Pin
     - Why it is there
   * - ``dronekit``
     - 2.9.2
     - High-level ``Vehicle`` API used by ``DroneKitController``. Unmaintained and
       only importable on Python ≤ 3.9.
   * - ``dronekit-sitl``
     - 3.3.0
     - Downloads and launches the ArduCopter 3.3 simulator.
   * - ``pymavlink``
     - 2.4.8
     - MAVLink message construction (yaw command). Old enough to build on 3.7.
   * - ``pyserial``
     - 3.5
     - Serial access for Pixhawk over USB.
   * - ``future``, ``monotonic``, ``psutil``, ``six``
     - various
     - Needed by DroneKit / dronekit-sitl (``import dronekit`` fails without ``future``).

dyopilot environment — Python 3.12+
-----------------------------------

``pip install -e ".[dyopilot]"``

.. list-table::
   :header-rows: 1
   :widths: 24 12 64

   * - Package
     - Pin
     - Why it is there
   * - ``dronekit-sitl``
     - 3.3.0
     - Only for ``start_default()`` / ``connection_string()`` / ``stop()``.
   * - ``pymavlink``
     - 2.4.49
     - All MAVLink traffic. A modern release is required: 2.4.8 does not build
       on Python 3.12.
   * - ``pyserial``
     - 3.5
     - Serial access for Pixhawk over USB.

``dronekit-sitl`` declares ``dronekit`` as a dependency in its package
metadata, so ``pip`` installs it into this environment too. It is never
imported: ``dronekit_sitl``'s runtime code does not import ``dronekit`` (only
its unused ``forwarder.py`` does). Seeing ``dronekit==2.9.2`` in ``pip list``
here is expected.

Documentation environment — Python 3.12+
----------------------------------------

``pip install -e ".[docs]"``

.. list-table::
   :header-rows: 1
   :widths: 24 12 64

   * - Package
     - Pin
     - Why it is there
   * - ``sphinx``
     - 9.1.0
     - Documentation builder.
   * - ``furo``
     - 2025.12.19
     - HTML theme.
   * - ``pymavlink``
     - 2.4.49
     - Real (not mocked) because the dyopilot driver evaluates ``mavutil``
       constants when imported.

DroneKit and ``dronekit_sitl`` are mocked by ``docs/conf.py``
(``autodoc_mock_imports``), so the Python 3.7 stack is not needed to build the
docs.

Voice — optional extra
----------------------

``pip install -e ".[dyopilot,voice]"``

.. list-table::
   :header-rows: 1
   :widths: 24 12 64

   * - Package
     - Pin
     - Why it is there
   * - ``vosk``
     - >=0.3.44
     - Offline speech recognition for the web console's voice mode. Optional: the
       rest of the project never imports it.

Vosk's model is not a Python package: ``vosk-model-small-en-us-0.15`` (about 40 MB) is
downloaded once, on first use, to ``~/.cache/dyodrone/vosk`` (``DYODRONE_CACHE``
moves it, ``--vosk-model`` points at an existing copy). Python 3.7 support for
the extra is best effort; voice is developed and tested on 3.12.

Test environment
----------------

``pip install -e ".[dyopilot,test]"`` (or ``".[dronekit,test]"``). ``test`` adds
``pytest`` (>=7.4,<9; 7.4 is the last line that supports Python 3.7). The
``docs`` build test also needs the ``docs`` extra.

Build backend
-------------

``setuptools>=64,<69``: 68 is the last release that builds on Python 3.7, and
64 is the first with editable installs for ``pyproject.toml`` projects.

Web console
-----------

``dyodrone.gui`` uses only the Python standard
library (``http.server``, ``threading``, ``json``); the page is one HTML file
with inline CSS and JavaScript and loads nothing from the network.

External runtime pieces
-----------------------

ArduCopter 3.3 SITL binary
   Downloaded on first use to ``~/.dronekit/sitl`` by ``dronekit_sitl``.

QGroundControl (optional)
   Receives telemetry over UDP from the GCS proxy; see :doc:`../guide/proxy`.
