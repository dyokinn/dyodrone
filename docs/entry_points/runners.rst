Runners
=======

``tox.ini`` defines one environment per task, so "which Python, which
dependencies" is written down instead of remembered. Run one with
``tox -e <name>``; ``tox`` alone runs ``dyopilot`` and ``dronekit``.

.. list-table::
   :header-rows: 1
   :widths: 22 14 64

   * - Environment
     - Python
     - What it does
   * - ``dyopilot``
     - 3.12
     - Unit tests with the ``dyopilot`` and ``test`` extras (dyopilot driver, web console, CLI).
   * - ``dronekit``
     - 3.7
     - Unit tests with the ``dronekit`` and ``test`` extras (everything above plus the DroneKit driver).
   * - ``sitl``
     - 3.12
     - Live-simulator tests (``pytest -m sitl``): needs the ArduCopter SITL binary and ~1 minute.
   * - ``sitl-dronekit``
     - 3.7
     - The same against the DroneKit driver.
   * - ``docs``
     - 3.12
     - Builds this documentation into ``docs/_build/html`` with ``sphinx-build -W`` (warnings are errors).

.. code-block:: bash

   tox -e docs                 # build the docs
   tox -e dyopilot -- -k gui   # extra arguments go to pytest
   tox -e dronekit             # needs a Python 3.7 interpreter on PATH

Interpreters
------------

tox needs ``python3.12`` and ``python3.7`` on ``PATH``. With ``pyenv``:

.. code-block:: bash

   pyenv install 3.12 3.7.17
   pyenv local 3.12 3.7.17     # writes .python-version, exposes both to tox

The Python 3.7 environments pin ``VIRTUALENV_PIP=23.0.1`` and
``VIRTUALENV_SETUPTOOLS=68.0.0`` in ``tox.ini``: the pip and setuptools that
virtualenv seeds by default no longer run on 3.7 (68.0.0 is the last setuptools
that does).

Without tox
-----------

Each environment is just an install plus a command:

.. code-block:: bash

   pip install -e ".[dyopilot,test]" && pytest          # unit tests
   pip install -e ".[docs]" && sphinx-build -W -b html docs docs/_build/html
