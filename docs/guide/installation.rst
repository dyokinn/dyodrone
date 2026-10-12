Installation
============

dyodrone needs **two** Python environments, one per backend family, because
DroneKit cannot be imported on Python 3.10+ (see :doc:`how` for the reasoning).
You only need the environment for the backends you actually use.

.. list-table::
   :header-rows: 1

   * - Environment
     - Python
     - Requirements file
     - Backends
   * - DroneKit
     - 3.7
     - ``dronekit_version/requirements-3.7.17.txt``
     - ``dronekit-sitl``, ``dronekit-pixhawk``
   * - dyopilot
     - 3.12+
     - ``dyopilot_version/requirements.txt``
     - ``dyopilot-sitl``, ``dyopilot-pixhawk``
   * - Docs
     - 3.12+
     - ``docs/requirements.txt``
     - — (only for building this documentation)

DroneKit environment (Python 3.7)
---------------------------------

.. code-block:: bash

   python3.7 -m venv .venv-dronekit
   source .venv-dronekit/bin/activate
   pip install -r dronekit_version/requirements-3.7.17.txt
   python entry_points/drone_cli.py --backend dronekit-sitl

If you manage interpreters with ``pyenv``, point ``python3.7`` at a 3.7.x
install (the requirements file is named after 3.7.17).

dyopilot environment (Python 3.12+)
-----------------------------------

.. code-block:: bash

   python3.12 -m venv .venv-dyopilot
   source .venv-dyopilot/bin/activate
   pip install -r dyopilot_version/requirements.txt
   python entry_points/drone_cli.py --backend dyopilot-sitl

``pip`` will also install ``dronekit`` here, because ``dronekit-sitl`` declares
it as a dependency. It is never imported by ``dyopilot_version`` and is harmless
— see :doc:`../project/dependencies`.

First run: the SITL binary
--------------------------

Both ``*-sitl`` backends start the ArduCopter 3.3 simulator through
``dronekit_sitl``. On the very first run it downloads the simulator binary to
``~/.dronekit/sitl`` (from ``dronekit-assets.s3.amazonaws.com``), so that run
needs network access and starts slowly. Later runs print "SITL already
Downloaded and Extracted" and boot immediately.

Building the documentation
--------------------------

.. code-block:: bash

   ./entry_points/build_docs.sh --open

This creates its own ``.venv-docs``; see :doc:`../entry_points/build_docs`.

Web console
-----------

Either environment can also run the browser console, which needs no extra
packages:

.. code-block:: bash

   python entry_points/drone_gui.py        # opens http://127.0.0.1:8765/?token=…

See :doc:`../entry_points/drone_gui`.

Checking the install
--------------------

.. code-block:: bash

   python entry_points/drone_cli.py --help                  # lists the four backends
   python entry_points/drone_cli.py --backend dyopilot-sitl # 3.12 env: telemetry should appear

The first telemetry values show ``unknown`` for a few seconds: the simulated GPS
needs roughly 6–10 seconds after boot to report a 3D fix.
