Contributing
============

Adding a backend
----------------

The CLI only knows :py:class:`drone_controller.DroneController`. A new backend
is a subclass plus three small edits.

#. **Implement the controller.** Put it in the matching package
   (``dronekit_version/`` or ``dyopilot_version/``), or a new package if it
   needs a different environment.

   * Reuse the family base class (``_DroneKitBase`` or ``_PyMAVLinkBase``) and
     override only ``connect()``, plus ``close()`` if you own extra resources
     (a simulator process, a proxy).
   * Keep teardown order: stop the proxy, close the connection, then stop the
     simulator.
   * For raw pymavlink backends, call ``_open_master(conn_str, proxy=...)``
     from ``connect()`` — it waits for a heartbeat, requests data streams and
     starts the reader thread.

#. **Register it in the CLI** (``entry_points/drone_cli.py``):

   * add the name to ``--backend`` ``choices``;
   * add a default to ``_DEFAULT_CONNECT`` if it takes ``--connect``;
   * add a branch in ``build_controller()`` that imports the class **inside
     the branch** (never at module top), so a backend's dependencies are only
     imported when it is selected;
   * if it cannot run on current Python, gate it like ``_require_python37``.

#. **Document it.** Add an autodoc entry under ``docs/api/``, a row in the
   backend tables in :doc:`../guide/how` and :doc:`/index`, and a note in
   :doc:`design_decisions` if you made a non-obvious choice.

Conventions used in the code
----------------------------

* ``from __future__ import annotations`` at the top of every module.
* NumPy-style docstrings (``Parameters`` / ``----------``); rendered by
  ``sphinx.ext.napoleon``.
* Backend-specific logic stays out of ``drone_controller.py`` and the CLI.
* Flight commands are fire-and-forget except ``takeoff`` and ``land``, which
  block until the mode change is confirmed.

Verifying changes
-----------------

There is no automated test suite yet; verification is done against the
simulator. A minimal check of a dyopilot backend, from the dyopilot
environment:

.. code-block:: python

   import time
   from dyopilot_version.dyopilot_sitl_controller import DyopilotSITLController

   c = DyopilotSITLController(gcs_port=None)
   c.connect()
   try:
       c.arm_and_takeoff(10)
       time.sleep(10)
       print("\n".join(c.status_lines()))   # Mode: GUIDED, Armed: True, agl≈10 m
       c.move_forward(5)
       c.rotate_right(90)
       c.land()
   finally:
       c.close()                             # stops reader, proxy and simulator

Run the equivalent with ``DronekitSITLController`` in the Python 3.7 environment
to confirm the DroneKit side did not regress. Then rebuild the docs:

.. code-block:: bash

   ./entry_points/build_docs.sh --clean

The build treats warnings as errors, so a broken cross-reference fails it.
