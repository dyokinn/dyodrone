QGroundControl Proxy
====================

Both SITL backends (``dronekit-sitl`` and ``dyopilot-sitl``) include a built-in UDP proxy that forwards live MAVLink telemetry to QGroundControl. No MAVProxy, no extra processes, no manual QGC configuration.

How it works
------------

When the proxy is active, the active backend intercepts every MAVLink frame it receives from SITL and forwards the raw bytes to QGC over UDP. The reader differs per backend, but both feed the same ``GCSProxy.forward(raw_bytes)``:

::

   SITL ──TCP──► backend's message reader
                       │  (DroneKit: vehicle.on_message('*') / dyopilot: MAVLinkReader)
                       ▼
                  GCSProxy.forward()
                       │  UDP sendto(gcs_host, gcs_port)
                       ▼
                  QGroundControl

``dronekit-sitl`` attaches a ``'*'`` wildcard listener to the DroneKit vehicle object; ``dyopilot-sitl`` passes ``GCSProxy.forward`` as the ``on_frame`` callback to its own ``MAVLinkReader`` background thread. Either way, every received frame — ``HEARTBEAT``, ``GLOBAL_POSITION_INT``, ``SYS_STATUS``, ``VFR_HUD``, everything QGC needs — has its original bytes (``get_msgbuf()``) sent unmodified, so QGC sees exactly what SITL sent.

Starting with the proxy
-----------------------

.. code-block:: bash

   # Default — proxy on 127.0.0.1:14550 (QGC on same machine)
   python entry_points/drone_cli.py

   # Custom port
   python entry_points/drone_cli.py --gcs-port 5600

   # QGC on another machine
   python entry_points/drone_cli.py --gcs-host 192.168.1.50

   # Broadcast to entire LAN
   python entry_points/drone_cli.py --gcs-host 255.255.255.255

   # Disable proxy
   python entry_points/drone_cli.py --gcs-port 0

The CLI screen shows the proxy target while it is active:

::

   Connection: tcp:127.0.0.1:5760
   GCS Proxy: → 127.0.0.1:14550  (QGC ready)

Connecting QGroundControl
-------------------------

Same machine (default)
~~~~~~~~~~~~~~~~~~~~~~

QGC must be configured to listen for incoming UDP on port 14550.

**Application Settings → Comm Links → Add**

============== =====
Field          Value
============== =====
Type           UDP
Listening Port 14550
Auto Connect   ✓
============== =====

Start the CLI first, then open QGC — or the other way around. QGC auto-connects as soon as it receives the first ``HEARTBEAT`` frame.

Different machine on the same LAN
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``--gcs-host <ip>`` with the specific IP of the machine running QGC, or ``--gcs-host 255.255.255.255`` to broadcast to all LAN hosts.

QGC on the remote machine needs the same Comm Link configuration (UDP, port 14550, auto-connect). No target address is required in QGC — it responds to the source of the telemetry packets.

Showing the drone on the map
----------------------------

SITL starts with a default home position of **Canberra, Australia** (``-35.363261, 149.165230``). Once QGC connects, it centers the map there automatically.

To place the drone at a custom location, the ``--home`` flag can be added to the SITL launch args. This is not yet exposed as a CLI flag — see :doc:`arch` for where ``start_default()`` is called if you want to add it.

Limitations
-----------

============ =======================================================================================================================================================================================
Direction    SITL → QGC only (telemetry / observation)
QGC commands Not forwarded back to SITL. Use the CLI to control the vehicle.
Why          The active backend (DroneKit or dyopilot) is the primary flight controller. Routing QGC MAVLink commands back to SITL alongside the CLI's own commands would create conflicting inputs.
============ =======================================================================================================================================================================================

QGC can be used to monitor telemetry, view the map, inspect parameters, and observe flight in real time. All control commands go through the CLI.

Troubleshooting
---------------

**QGC link shows "connected" but vehicle shows disconnected**

- The UDP socket reached QGC but no ``HEARTBEAT`` arrived yet. Wait 2–3 seconds after the CLI connects — SITL takes a moment to start emitting heartbeats.

**No UDP packets reaching QGC on the same machine**

- Some OS configurations block UDP to ``127.0.0.1`` on port 14550. Try a different port: ``--gcs-port 14560``.

**No UDP packets reaching QGC on a remote machine with broadcast**

- LAN routers and managed switches often block ``255.255.255.255``. Use a specific IP: ``--gcs-host 192.168.x.x``.

**Drone doesn't appear on the map**

- Confirm QGC has internet access for map tiles.
- Click the vehicle icon in the QGC toolbar to fly the map to the drone's home coordinates.
