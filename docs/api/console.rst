Shared console logic
====================

Backend selection and command handling used by both :doc:`../entry_points/drone_cli`
and :doc:`../entry_points/drone_gui`. No UI toolkit, Python 3.7 compatible.

.. automodule:: dyodrone.core.factory
   :members: BACKENDS, DEFAULT_CONNECT, DRONEKIT_BACKENDS, BackendUnavailable, require_python37, create_controller

.. automodule:: dyodrone.core.commands
   :members: COMMAND_HELP, handle_command
