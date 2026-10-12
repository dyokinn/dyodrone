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
   * - ``tox -e <name>``
     - Runners: tests on Python 3.7 / 3.12, live-simulator tests, the docs build
     - :doc:`runners`

Repository layout
-----------------

::

   dyodrone/
   ├── pyproject.toml                 ← metadata, extras (dronekit, dyopilot, docs, test), console scripts, pytest config
   ├── tox.ini                        ← runners: which Python for which task
   ├── src/dyodrone/
   │   ├── core/                      ← controller ABC, commands, targets, GCS proxy, factory
   │   ├── drivers/                   ← dronekit_driver (Python 3.7), dyopilot_driver + reader (pymavlink)
   │   ├── cli.py                     ← dyodrone-cli
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
   tox -e docs

.. toctree::
   :maxdepth: 1
   :hidden:

   dyodrone_cli
   dyodrone_gui
   runners
