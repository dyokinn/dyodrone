Flight plans
============

A flight plan is a plain text file: one console command per line. Run it from
the web console (:doc:`../entry_points/dyodrone_gui`) or with no UI using
:doc:`../entry_points/dyodrone_plan`.

Format
------

.. code-block:: text

   # square at 10 m — comments start with '#'
   takeoff 10
   forward 20
   right 90
   wait 5            # optional pause, seconds
   land

* One command per line, exactly as you would type it at the console:
  ``takeoff``, ``altitude``, ``forward``, ``back``, ``left``, ``right``, ``land``.
* ``wait <seconds>`` is the only extra: hold position for that long.
* Blank lines and ``#`` comments (also after a command) are ignored; verbs are
  case-insensitive.
* ``quit``, ``info`` and ``help`` are console commands, not plan steps.
* Every problem is reported with its **line number**, all at once, before anything
  flies: ``line 3: 'x' is not a number (forward: distance in meters)``.

How a step finishes
-------------------

``forward 5`` returns the moment the command is *sent*; the vehicle is still
flying. A plan therefore does not fire the next line blindly — it checks that
the vehicle actually did what was asked:

1. **Snapshot** the telemetry before the command.
2. **Expect**: compute where the vehicle should end up.
3. **Send** the command.
4. Every **3 seconds**, read fresh telemetry and compare it with the expectation.
5. When it matches, start the next step. If it does not within the step timeout
   (120 s), the plan stops.

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Step
     - Done when
   * - ``takeoff N``
     - armed, and altitude within the margin of N
   * - ``altitude N``
     - altitude within the margin of N
   * - ``forward M`` / ``back M``
     - position within the margin of the point M metres ahead of / behind the
       start, along the heading at the snapshot
   * - ``left D`` / ``right D``
     - heading within the margin of the start heading ∓/± D (compared around
       the circle, so 350° + 20° → 10° works)
   * - ``land``
     - altitude below the landed threshold
   * - ``wait S``
     - S seconds have passed (no telemetry involved)

The data comes from MAVLink messages the connection already receives
(``GLOBAL_POSITION_INT`` for position and relative altitude, ``ATTITUDE`` for
heading, ``HEARTBEAT`` for armed state and mode), so no extra requests are made.

The 10 % margin
~~~~~~~~~~~~~~~

"Within the margin" means ``|measured − expected| ≤ max(10 % × commanded amount, floor)``.
The floors keep small commands achievable: 0.5 m for distance and altitude,
2° for heading, and 0.3 m for the landed check. So ``forward 20`` is done within
2 m; ``forward 2`` within 0.5 m (not 0.2 m, which is below GPS noise); ``right 90``
within 9°; ``land`` from 10 m when below 1 m. The margin is ``--margin`` /
``--plan-margin`` and the polling interval ``--poll`` / ``--plan-poll``.

Stopping and failing
--------------------

* The plan **stops at the first failing step**: a rejected command (``Takeoff
  failed: …``), a step that has not completed ``--step-timeout`` seconds after
  it was sent, or telemetry that never arrives.
* It never lands on its own. **Stop** simply stops sending commands — the vehicle
  keeps hovering. Use ``land`` in the plan or **Land now** in the web console.
* **Pause** holds before the next step (a command already in progress finishes
  first); **Resume** continues.

Recording a plan from the console
---------------------------------

The web console remembers every flight command you (or voice mode) ran that
completed without error. **From log** puts them in the plan editor as plan text;
**Download** saves the file. No timing is stored — completion is decided by
telemetry, so a replay waits as long as the flight needs. Plan steps themselves
and emergency landings are not recorded.

Typical workflow: fly it once by hand (or by voice) → *From log* → tidy the text →
*Run*, or save it and run it later with ``dyodrone-plan``.
