Shared console logic
====================

Backend selection and command handling used by both :doc:`../entry_points/drone_cli`
and :doc:`../entry_points/drone_gui`. No UI toolkit, Python 3.7 compatible.

.. automodule:: drone_console
   :members: BACKENDS, DEFAULT_CONNECT, DRONEKIT_BACKENDS, COMMAND_HELP, BackendUnavailable, require_python37, create_controller, handle_command
