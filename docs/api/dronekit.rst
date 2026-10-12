DroneKit backends
=================

Require **Python 3.7** — see :doc:`../guide/how`. On other interpreters these pages
are built with ``dronekit`` mocked, so signatures are shown but nothing here is
importable at runtime.

Shared flight logic
-------------------

.. autoclass:: dronekit_version.dronekit_controller._DroneKitBase
   :members:
   :show-inheritance:

SITL backend
------------

.. autoclass:: dronekit_version.dronekit_sitl_controller.DronekitSITLController
   :members:
   :show-inheritance:

Pixhawk backend
---------------

.. autoclass:: dronekit_version.dronekit_pixhawk_controller.DronekitPixhawkController
   :members:
   :show-inheritance:

GCS proxy
---------

Shared by both backend families — see :doc:`../guide/proxy`.

.. autoclass:: dronekit_version.gcs_proxy.GCSProxy
   :members:
