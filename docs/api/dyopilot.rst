dyopilot (pymavlink) backends
=============================

Run on **Python 3.12+** and never import DroneKit — see :doc:`../guide/how`.

Shared flight logic
-------------------

.. autoclass:: dyopilot_version.dyopilot_controller._PyMAVLinkBase
   :members:
   :show-inheritance:

SITL backend
------------

.. autoclass:: dyopilot_version.dyopilot_sitl_controller.DyopilotSITLController
   :members:
   :show-inheritance:

Pixhawk backend
---------------

.. autoclass:: dyopilot_version.dyopilot_pixhawk_controller.DyopilotPixhawkController
   :members:
   :show-inheritance:

Message reader
--------------

.. autoclass:: dyopilot_version.pymavlink_reader.MAVLinkReader
   :members:
