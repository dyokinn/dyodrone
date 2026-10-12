.. dyodrone documentation master file, created by
   sphinx-quickstart on Mon Oct 12 14:08:42 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

dyodrone documentation
======================

An interactive terminal CLI for monitoring and commanding a drone, with
interchangeable backends behind one abstract interface
(:py:class:`drone_controller.DroneController`).

.. list-table::
   :header-rows: 1

   * - ``--backend``
     - Drives the vehicle with
     - Python
   * - ``dronekit-sitl``
     - DroneKit ``Vehicle`` against a built-in ArduCopter 3.3 SITL
     - 3.7
   * - ``dronekit-pixhawk``
     - DroneKit ``Vehicle`` against a real Pixhawk
     - 3.7
   * - ``dyopilot-sitl``
     - Raw pymavlink against a built-in ArduCopter 3.3 SITL
     - 3.12+
   * - ``dyopilot-pixhawk``
     - Raw pymavlink against a real Pixhawk
     - 3.12+

The two backend families live in separate virtual environments because
DroneKit cannot be imported on Python 3.10+ — see :doc:`guide/how` for the setup.

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

   ./entry_points/build_docs.sh            # creates .venv-docs, installs deps, builds docs/_build/html
   ./entry_points/build_docs.sh --clean --open

The script wraps ``make -C docs html`` and treats Sphinx warnings as errors.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
