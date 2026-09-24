# MeshCore Proxy

Shares **one** MeshCore radio (USB) over TCP between several programs, for example the
[meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) integration and the **MeshCore Bot** add-on.

A serial port can only be opened by one program at a time. This proxy opens it once and lets every
client talk to the radio over `localhost:5010` with exactly the same protocol as over USB.

Needs a MeshCore radio with companion (USB) firmware connected to your Home Assistant machine, for example the [Seeed XIAO ESP32S3 + Wio-SX1262 kit](https://www.seeedstudio.com/XIAO-ESP32S3-for-Meshtastic-LoRa-with-3D-Printed-Enclosure-p-6314.html).

Read the **Documentation** tab for details.
