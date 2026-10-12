dyopilot (pymavlink) backends
=============================

Run on **Python 3.12+** and never import DroneKit — see :doc:`../guide/how`.

Shared flight logic
-------------------

.. autoclass:: dyodrone.drivers.dyopilot_driver._PyMAVLinkBase
   :members:
   :show-inheritance:

SITL backend
------------

.. autoclass:: dyodrone.drivers.dyopilot_sitl.DyopilotSITLController
   :members:
   :show-inheritance:

Pixhawk backend
---------------

.. autoclass:: dyodrone.drivers.dyopilot_pixhawk.DyopilotPixhawkController
   :members:
   :show-inheritance:

Message reader
--------------

.. autoclass:: dyodrone.drivers.dyopilot_reader.MAVLinkReader
   :members:
