DroneKit backends
=================

Require **Python 3.7** — see :doc:`../guide/how`. On other interpreters these pages
are built with ``dronekit`` mocked, so signatures are shown but nothing here is
importable at runtime.

Shared flight logic
-------------------

.. autoclass:: dyodrone.drivers.dronekit_driver._DroneKitBase
   :members:
   :show-inheritance:

SITL backend
------------

.. autoclass:: dyodrone.drivers.dronekit_sitl.DronekitSITLController
   :members:
   :show-inheritance:

Pixhawk backend
---------------

.. autoclass:: dyodrone.drivers.dronekit_pixhawk.DronekitPixhawkController
   :members:
   :show-inheritance:

GCS proxy
---------

Shared by both backend families — see :doc:`../guide/proxy`.

.. autoclass:: dyodrone.core.proxy.GCSProxy
   :members:
