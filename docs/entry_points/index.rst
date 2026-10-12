Entry points
============

An *entry point* is a file you run directly. They all live in the
``entry_points/`` folder at the repo root; everything else in the repo is
library code that those scripts import (or documentation).

.. list-table::
   :header-rows: 1

   * - Entry point
     - What it does
     - Details
   * - ``entry_points/drone_cli.py``
     - Interactive curses console to monitor and command a drone
     - :doc:`drone_cli`
   * - ``entry_points/drone_gui.py``
     - Browser console: live vehicle info, command prompt, Simulator/Pixhawk toggle
     - :doc:`drone_gui`
   * - ``entry_points/build_docs.sh``
     - Builds this documentation with Sphinx and Furo
     - :doc:`build_docs`

Repository layout
-----------------

::

   dyodrone/
   ├── entry_points/                  ← everything you run lives here
   │   ├── drone_cli.py
   │   ├── drone_gui.py
   │   └── build_docs.sh
   ├── drone_controller.py            ← DroneController (ABC) the front ends depend on
   ├── drone_console.py               ← backend selection + command handling shared by CLI and GUI
   ├── drone_gui/                     ← web console: session, HTTP server, static page
   ├── dronekit_version/              ← DroneKit backends (Python 3.7)
   │   ├── dronekit_controller.py
   │   ├── dronekit_sitl_controller.py
   │   ├── dronekit_pixhawk_controller.py
   │   ├── gcs_proxy.py
   │   └── requirements-3.7.17.txt
   ├── dyopilot_version/              ← pymavlink backends (Python 3.12+)
   │   ├── dyopilot_controller.py
   │   ├── dyopilot_sitl_controller.py
   │   ├── dyopilot_pixhawk_controller.py
   │   ├── pymavlink_reader.py
   │   └── requirements.txt
   └── docs/                          ← this documentation (Sphinx + Furo)
       ├── guide/                     ← installation, how, arch, proxy, troubleshooting
       ├── entry_points/              ← this section
       ├── api/                       ← autodoc reference
       └── project/                   ← dependencies, design decisions, contributing, history, glossary

Running from anywhere
---------------------

Entry points add the repo root to ``sys.path`` themselves, so they work from
any current directory, for example:

.. code-block:: bash

   python entry_points/drone_cli.py --backend dyopilot-sitl
   ./entry_points/build_docs.sh --open

.. toctree::
   :maxdepth: 1
   :hidden:

   drone_cli
   drone_gui
   build_docs
