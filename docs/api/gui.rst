Web console
===========

The package behind :doc:`../entry_points/drone_gui`.

Session
-------

.. autoclass:: drone_gui.session.ConsoleSession
   :members: connect, disconnect, submit, snapshot, close

.. autoclass:: drone_gui.session.SessionError

.. autofunction:: drone_gui.session.default_family

Server
------

.. autoclass:: drone_gui.server.ConsoleServer
   :members: url
