Core
====

Everything the front ends depend on: the controller contract, targets, command
handling, driver selection and the GCS proxy. No UI toolkit; Python 3.7
compatible. See :doc:`../guide/arch` for the layering.

Controller interface
--------------------

.. automodule:: dyodrone.core.controller
   :members:
   :undoc-members:

Targets
-------

.. automodule:: dyodrone.core.targets
   :members: TARGETS, Target, SitlTarget, ExternalTarget, make_target

Driver selection
----------------

.. automodule:: dyodrone.core.factory
   :members: DRIVERS, DEFAULT_CONNECTION, DEFAULT_GCS_PORT, BackendUnavailable, default_driver, require_python37, create_controller

Telemetry
---------

.. automodule:: dyodrone.core.telemetry
   :members:

Flight plans
------------

.. automodule:: dyodrone.core.plan
   :members: PLAN_VERBS, Step, PlanError, parse_plan, format_plan

.. automodule:: dyodrone.core.expect
   :members: Tolerances, MissingTelemetry, CheckResult, Expectation, expected_after, describe_step, angle_error_deg

.. automodule:: dyodrone.core.plan_runner
   :members: PlanEvent, PlanRunner

Voice grammar
-------------

.. automodule:: dyodrone.core.voice
   :members: KEYWORDS, VOCABULARY, parse_number, slice_commands

Commands
--------

Shared by :doc:`../entry_points/dyodrone_cli` and :doc:`../entry_points/dyodrone_gui`.

.. automodule:: dyodrone.core.commands
   :members: COMMAND_HELP, handle_command

GCS proxy
---------

Shared by both drivers — see :doc:`../guide/proxy`.

.. autoclass:: dyodrone.core.proxy.GCSProxy
   :members:
