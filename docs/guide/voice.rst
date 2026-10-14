Voice commands
==============

Voice mode listens to your microphone and turns what you say into the same
commands as the console, using **exactly the console keywords**. Speech
recognition is **offline** (Vosk): audio is processed on your machine and never
leaves it.

.. code-block:: text

   "takeoff ten"                     →  takeoff 10
   "forward twenty five"             →  forward 25
   "right ninety"                    →  right 90
   "altitude one hundred twenty"     →  altitude 120
   "forward two point five"          →  forward 2.5
   "takeoff ten forward five land"   →  takeoff 10, forward 5, land

Keywords: ``takeoff``, ``altitude``, ``forward``, ``back``, ``left``, ``right``,
``land``, ``quit``, ``exit``. Numbers are spoken as words: ``zero`` to
``nineteen``, tens (``twenty five``), ``hundred``, and decimals digit by digit
after ``point``. You can say several commands in one breath; the transcript is
sliced at each keyword. A keyword without a usable number (``forward``,
``right twenty twenty``) is dropped, with a note in the console.

Setup
-----

.. code-block:: bash

   pip install -e ".[dyopilot,voice]"       # adds the vosk package
   dyodrone-gui                              # then switch Voice on

``runners/launch_web.sh`` does this for you. The first time you switch Voice on,
the small English model (``vosk-model-small-en-us-0.15``, about 40 MB) is
downloaded once to ``~/.cache/dyodrone/vosk`` (set ``DYODRONE_CACHE`` to move it);
progress appears in the console, and it takes a few seconds to a few minutes
depending on your connection. Already have it?
Start with ``dyodrone-gui --vosk-model /path/to/model``. If Vosk or the model is
unavailable, the Voice switch turns itself back off and the console says why.

Safety: the cancel window
-------------------------

Mis-heard speech must not fly the vehicle. Every recognised command appears in
the **Voice** panel with a countdown and a **Cancel** button, and only runs after
``--voice-delay`` seconds (default **2**). **Cancel all** drops everything
pending. ``land`` is the exception: it runs immediately. A pulsing "Listening"
indicator is shown whenever the microphone is open.

Voice commands obey the same rules as typing: they are refused if the Voice
switch is off, and locked out while a flight plan runs. **Land now** clears the
pending list.

How it works
------------

#. The page opens the microphone (browsers allow this on ``localhost``), converts
   the audio to 16 kHz 16-bit mono PCM, and posts ~0.25 s chunks to
   ``POST /api/voice/audio``.
#. The server feeds a Vosk recognizer **restricted to the keyword and number
   vocabulary**, which makes it far more accurate than open dictation. Partial
   results are shown live; each finished utterance is sliced into commands by
   :mod:`dyodrone.core.voice`.
#. Commands enter the pending list and, after the delay, go through the normal
   command path (``source="voice"``).

Limits
------

* English only; small model, so speak clearly and pause briefly between
  utterances (the recogniser finalises a phrase after a short silence).
* ``take off`` (two words) is not accepted — say ``takeoff`` — because the
  keywords are exactly the console's.
* The microphone needs a secure context: ``http://127.0.0.1`` and ``localhost``
  are fine; a console served on another address is not.
