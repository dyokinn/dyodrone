Entry points
============

An *entry point* is something you run. They are installed with the package as
console scripts, so they are on your ``PATH`` once you ``pip install -e .`` an
environment (see :doc:`../guide/installation`); there are no scripts to locate
and no ``sys.path`` tricks.

.. list-table::
   :header-rows: 1

   * - Command
     - What it does
     - Details
   * - ``dyodrone-cli`` (or ``python -m dyodrone``)
     - Interactive curses console to monitor and command a drone
     - :doc:`dyodrone_cli`
   * - ``dyodrone-gui``
     - Browser console: live vehicle info, command prompt, Simulator/Pixhawk toggle
     - :doc:`dyodrone_gui`
   * - ``dyodrone-plan``
     - Runs a flight-plan text file with no UI (closed-loop, verified by telemetry)
     - :doc:`dyodrone_plan`
   * - ``runners/*.sh``
     - Scripts to build the docs, run all tests, and launch the web console (they call tox / the console script)
     - :doc:`runners`

Repository layout
-----------------

::

   dyodrone/
   ├── pyproject.toml                 ← metadata, extras (dronekit, dyopilot, docs, test), console scripts, pytest config
   ├── tox.ini                        ← environments: which Python for which task
   ├── runners/                       ← build_docs.sh, run_tests.sh, launch_web.sh
   ├── src/dyodrone/
   │   ├── core/                      ← controller ABC, commands, targets, GCS proxy, factory
   │   ├── drivers/                   ← dronekit_driver (Python 3.7), dyopilot_driver + reader (pymavlink)
   │   ├── cli.py, plan_cli.py        ← dyodrone-cli, dyodrone-plan
   │   └── gui/                       ← dyodrone-gui: session, HTTP server, static page
   ├── tests/                         ← pytest suite, one folder per layer
   └── docs/                          ← this documentation (Sphinx + Furo)
       ├── guide/                     ← installation, how, arch, proxy, troubleshooting
       ├── entry_points/              ← this section
       ├── api/                       ← autodoc reference
       └── project/                   ← dependencies, design decisions, contributing, testing, history, glossary

Running from anywhere
---------------------

Once installed, the commands work from any directory:

.. code-block:: bash

   dyodrone-cli --driver dyopilot --target sitl
   dyodrone-gui --no-browser
   runners/build_docs.sh

.. toctree::
   :maxdepth: 1
   :hidden:

   dyodrone_cli
   dyodrone_gui
   dyodrone_plan
   runners
