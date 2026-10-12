Contributing
============

Setup
-----

.. code-block:: bash

   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dyopilot,test]"
   pytest

Run ``tox`` to exercise both Python 3.12 and 3.7 (see :doc:`../entry_points/runners`).
Code in ``dyodrone/core`` and ``dyodrone/gui`` must stay **Python 3.7 compatible**
(no walrus operator, no ``typing.Literal``/``Protocol``; keep
``from __future__ import annotations``), because the same package installs in
both environments.

Adding a target
---------------

A target supplies a connection string and cleans up after it.

#. Subclass :py:class:`dyodrone.core.targets.Target` in ``core/targets.py``:
   ``acquire()`` returns the connection string (starting anything it needs) and
   ``release()`` stops it and is safe to call twice.
#. Register its name in ``TARGETS`` and ``make_target()``.
#. Add tests in ``tests/core/test_targets.py``, document it in
   :doc:`../guide/how` (the driver/target table) and :doc:`../api/core`.

Drivers take any target, so nothing in the drivers changes. The web console's
toggle and the CLI's ``--target`` choices come from ``TARGETS``.

Adding a driver
---------------

#. Implement :py:class:`dyodrone.core.controller.DroneController` in
   ``drivers/<name>_driver.py`` with a constructor
   ``(target, proxy=None, …)``. In ``connect()`` call ``target.acquire()``; on any
   failure call ``close()`` and re-raise; in ``close()`` stop the proxy, then the
   connection, then ``target.release()``.
#. Add the name to ``DRIVERS`` and a branch in
   ``core/factory.create_controller()`` that imports the driver **inside the
   branch** (never at module top), so its dependencies are only imported when it
   is selected. If it cannot run on current Python, gate it like
   ``require_python37`` and raise ``BackendUnavailable``.
#. Add an extra for its dependencies in ``pyproject.toml`` and, if it needs a
   different interpreter, a tox environment.
#. Tests (a fake connection like ``tests/fakes.py`` for the unit tests, an opt-in
   ``sitl`` test) and docs (:doc:`../api/index`, :doc:`design_decisions`).

Conventions used in the code
----------------------------

* ``from __future__ import annotations`` at the top of every module.
* NumPy-style docstrings (``Parameters`` / ``----------``); rendered by
  ``sphinx.ext.napoleon``.
* Driver- and target-specific logic stays out of ``core/controller.py``,
  ``core/commands.py`` and both front ends.
* Flight commands are fire-and-forget except ``takeoff`` and ``land``, which
  block until the mode change is confirmed.

Verifying changes
-----------------

See :doc:`testing`. The short version:

.. code-block:: bash

   tox                   # unit tests on 3.12 and 3.7
   tox -e sitl           # live simulator, before touching a driver
   tox -e docs           # strict docs build (a broken cross-reference fails it)
