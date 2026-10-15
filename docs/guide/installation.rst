Installation
============

dyodrone needs **two** Python environments, one per driver, because DroneKit
cannot be imported on Python 3.10+ (see :doc:`how` for the reasoning). You only
need the environment for the driver you actually use. Both install the same
package; the *extra* you choose decides which libraries come with it.

.. list-table::
   :header-rows: 1

   * - Environment
     - Python
     - Install
     - Drivers
   * - DroneKit
     - 3.7
     - ``pip install -e ".[dronekit]"``
     - ``dronekit`` (and ``dyopilot``)
   * - dyopilot
     - 3.12+
     - ``pip install -e ".[dyopilot]"``
     - ``dyopilot``
   * - Tests
     - either
     - add ``,test``, e.g. ``".[dyopilot,test]"``
     - —
   * - Voice
     - 3.12+
     - add ``,voice``, e.g. ``".[dyopilot,voice]"`` (installs ``vosk``)
     - — (only for voice mode in the web console)
   * - Docs
     - 3.12+
     - ``pip install -e ".[docs]"``
     - — (only to build this documentation)

DroneKit environment (Python 3.7)
---------------------------------

.. code-block:: bash

   python3.7 -m venv .venv-dronekit
   source .venv-dronekit/bin/activate
   pip install -e ".[dronekit]"
   dyodrone-cli --driver dronekit --target sitl

If you manage interpreters with ``pyenv``, point ``python3.7`` at a 3.7.x
install.

dyopilot environment (Python 3.12+)
-----------------------------------

.. code-block:: bash

   python3.12 -m venv .venv-dyopilot
   source .venv-dyopilot/bin/activate
   pip install -e ".[dyopilot]"
   dyodrone-cli --driver dyopilot --target sitl

``pip`` will also install ``dronekit`` here, because ``dronekit-sitl`` declares
it as a dependency. It is never imported by the dyopilot driver and is harmless
— see :doc:`../project/dependencies`.

First run: the SITL binary
--------------------------

``--target sitl`` starts the ArduCopter 3.3 simulator through
``dronekit_sitl``. On the very first run it downloads the simulator binary to
``~/.dronekit/sitl`` (from ``dronekit-assets.s3.amazonaws.com``), so that run
needs network access and starts slowly. Later runs print "SITL already
Downloaded and Extracted" and boot immediately.

Web console
-----------

Either environment can also run the browser console, which needs no extra
packages:

.. code-block:: bash

   dyodrone-gui        # opens http://127.0.0.1:8765/?token=…

See :doc:`../entry_points/dyodrone_gui`.

Voice mode
----------

.. code-block:: bash

   pip install -e ".[dyopilot,voice]"
   dyodrone-gui          # switch Voice on; the speech model downloads once (~40 MB)

See :doc:`voice`.

Running the tests and building the docs
---------------------------------------

With tox (creates the right environments for you; see :doc:`../entry_points/runners`):

.. code-block:: bash

   tox -e dyopilot        # unit tests, Python 3.12
   tox -e dronekit        # unit tests, Python 3.7
   tox -e docs            # build the documentation

Checking the install
--------------------

.. code-block:: bash

   dyodrone-cli --help                          # lists --driver and --target
   dyodrone-cli --driver dyopilot --target sitl # 3.12 env: telemetry should appear

The first telemetry values show ``unknown`` for a few seconds: the simulated GPS
needs roughly 6–10 seconds after boot to report a 3D fix.
