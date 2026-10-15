.. dyodrone documentation master file, created by
   sphinx-quickstart on Mon Oct 12 14:08:42 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

dyodrone documentation
======================

Console and web front ends for commanding a drone. You pick a **driver** (the
flight-control library) and a **target** (what it connects to); both sit behind
one abstract interface
(:py:class:`dyodrone.core.controller.DroneController`).

.. list-table::
   :header-rows: 1

   * -
     - ``--target sitl``
     - ``--target pixhawk``
   * - ``--driver dronekit`` (Python 3.7)
     - DroneKit ``Vehicle`` against the built-in ArduCopter 3.3 simulator
     - DroneKit ``Vehicle`` against a real Pixhawk
   * - ``--driver dyopilot`` (Python 3.12+)
     - Raw pymavlink against the built-in simulator
     - Raw pymavlink against a real Pixhawk

The two drivers live in separate virtual environments because DroneKit cannot be
imported on Python 3.10+ — see :doc:`guide/how` for the setup.

.. code-block:: bash

   pip install -e ".[dyopilot]"                  # in a Python 3.12 environment
   dyodrone-cli --driver dyopilot --target sitl  # curses console
   dyodrone-gui                                  # browser console

.. toctree::
   :maxdepth: 2
   :caption: Guide

   guide/index

.. toctree::
   :maxdepth: 2
   :caption: Entry points

   entry_points/index

.. toctree::
   :maxdepth: 2
   :caption: API reference

   api/index

.. toctree::
   :maxdepth: 2
   :caption: Project

   project/index

Building these docs
-------------------

.. code-block:: bash

   tox -e docs                # creates a Python 3.12 environment and builds docs/_build/html

See :doc:`entry_points/runners`; without tox, ``pip install -e ".[docs]"`` then
``sphinx-build -W -b html docs docs/_build/html``.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
