# MeshCore Proxy – documentation

## Hardware

A MeshCore radio flashed with the **companion (USB)** firmware, connected by USB to the machine that runs
Home Assistant. The author uses the [Seeed XIAO ESP32S3 + Wio-SX1262 kit](https://www.seeedstudio.com/XIAO-ESP32S3-for-Meshtastic-LoRa-with-3D-Printed-Enclosure-p-6314.html) (sold as a Meshtastic
kit, flashed with MeshCore firmware from the [MeshCore project](https://github.com/meshcore-dev/MeshCore)).
Any other board that runs the MeshCore companion firmware over USB serial works the same way.

Typical clients: the **MeshCore Bot** add-on from this repository, the
[meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) integration and, through it, the
[MeshCore Chat](https://github.com/mwolter805/meshcore-ha-chat) panel.

## Set-up

1. Plug in the radio and set **Serial port** to its path. A `/dev/serial/by-id/usb-...` path is the most
   stable one. If the port cannot be found, the add-on log lists the paths that exist.
2. Start the add-on. The log shows `Luistert op 0.0.0.0:5010` (the proxy's log messages are Dutch).
3. Point every program that used the USB device at the proxy instead:
   - **MeshCore Bot** add-on: *Connection type* `tcp`, host `localhost`, port `5010`.
   - **meshcore-ha** integration: connection type TCP, host `localhost`, port `5010`.

Start the proxy first, so the clients find it when they start.

## Options

| Option | Meaning |
|---|---|
| Serial port | Path of the radio, for example `/dev/ttyACM0`. |
| Baud rate | 115200 for MeshCore companion firmware. |
| Listen port | TCP port for clients. Default 5010. |
| Turn ends after silence | See *Turns* below. Default 0.75 s. |
| Longest turn | Hard limit for one turn. Default 8 s. |
| Log level | `DEBUG` shows every turn. |

## Turns

The MeshCore companion protocol has no request id. If two clients sent a command at the same time and
both waited for "the next OK", each could pick up the other's answer and fail with random errors.

The proxy therefore gives a client a *turn* as soon as it sends something. During the turn:

- the radio's answers go live to that client only;
- the other clients get the same bytes a moment later (nothing is dropped);
- the turn ends after *Turn ends after silence* seconds without radio traffic, or after *Longest turn*.

Outside a turn, spontaneous events from the mesh (incoming messages, adverts) go to everyone at once.
The defaults work well; only change them if a client misses replies (raise the silence time) or feels slow
(lower it).

## Troubleshooting

| Problem | Try |
|---|---|
| `Serial port ... does not exist` | Radio not plugged in, or another path. Check the list in the log. |
| Add-on cannot open the port | Another add-on or integration still has the USB device open. Point it at the proxy instead. |
| Clients see random `ERR_CODE_ILLEGAL_ARG` errors | Raise *Turn ends after silence* to 1.5 s. |
