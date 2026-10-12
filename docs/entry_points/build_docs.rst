build_docs.sh
=============

Builds this documentation into ``docs/_build/html``. Warnings are treated as
errors (``sphinx-build -W``), so a clean exit means a clean build.

.. code-block:: bash

   ./entry_points/build_docs.sh [--clean] [--open]

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Effect
   * - ``--clean``
     - Remove ``docs/_build`` before building
   * - ``--open``
     - Open ``docs/_build/html/index.html`` in the default browser afterwards
   * - ``-h``, ``--help``
     - Show usage

Environment
-----------

``PYTHON``
   Interpreter used to create the docs virtualenv (Python 3.12+, default
   ``python3.12``). Only used the first time.

What it does
------------

#. Creates ``.venv-docs`` at the repo root if it does not exist.
#. Installs ``docs/requirements.txt`` into it, but only when that file is newer
   than the last successful install.
#. Runs ``python -m sphinx -b html -W --keep-going docs docs/_build/html``.

The DroneKit stack is mocked by ``docs/conf.py``, so building the docs does
not need the Python 3.7 environment.
