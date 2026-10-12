Dependencies
============

Each backend family has its own requirements file and its own virtual
environment. Nothing is shared at runtime.

DroneKit environment — Python 3.7
---------------------------------

``dronekit_version/requirements-3.7.17.txt``

.. list-table::
   :header-rows: 1
   :widths: 24 12 64

   * - Package
     - Pin
     - Why it is there
   * - ``dronekit``
     - 2.9.2
     - High-level ``Vehicle`` API used by ``_DroneKitBase``. Unmaintained and
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
   * - ``Cython``, ``future``, ``lxml``, ``monotonic``, ``psutil``, ``six``
     - various
     - Transitive dependencies of DroneKit / dronekit-sitl.

dyopilot environment — Python 3.12+
-----------------------------------

``dyopilot_version/requirements.txt``

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

``docs/requirements.txt``

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
     - Real (not mocked) because ``dyopilot_version`` evaluates ``mavutil``
       constants when imported.

DroneKit and ``dronekit_sitl`` are mocked by ``docs/conf.py``
(``autodoc_mock_imports``), so the Python 3.7 stack is not needed to build the
docs.

Web console
-----------

``drone_gui/`` and ``entry_points/drone_gui.py`` use only the Python standard
library (``http.server``, ``threading``, ``json``); the page is one HTML file
with inline CSS and JavaScript and loads nothing from the network.

External runtime pieces
-----------------------

ArduCopter 3.3 SITL binary
   Downloaded on first use to ``~/.dronekit/sitl`` by ``dronekit_sitl``.

QGroundControl (optional)
   Receives telemetry over UDP from the GCS proxy; see :doc:`../guide/proxy`.
