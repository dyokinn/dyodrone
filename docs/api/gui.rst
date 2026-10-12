Web console
===========

The package behind :doc:`../entry_points/drone_gui`.

Session
-------

.. autoclass:: dyodrone.gui.session.ConsoleSession
   :members: connect, disconnect, submit, snapshot, close

.. autoclass:: dyodrone.gui.session.SessionError

.. autofunction:: dyodrone.gui.session.default_family

Server
------

.. autoclass:: dyodrone.gui.server.ConsoleServer
   :members: url
