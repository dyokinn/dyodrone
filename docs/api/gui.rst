Web console
===========

The package behind :doc:`../entry_points/dyodrone_gui`.

Session
-------

.. autoclass:: dyodrone.gui.session.ConsoleSession
   :members: connect, disconnect, submit, set_inputs, emergency_land, plan_validate, plan_run, plan_pause, plan_resume, plan_stop, history_text, voice_audio, voice_cancel, snapshot, close

.. autoclass:: dyodrone.gui.session.SessionError

Server
------

.. autoclass:: dyodrone.gui.server.ConsoleServer
   :members: url

Speech engine
-------------

.. automodule:: dyodrone.gui.voice_engine
   :members: SAMPLE_RATE, EngineUnavailable, SpeechResult, SpeechEngine, VoskEngine, ensure_model, load_vosk_engine
