# MeshCore Bot

[agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot) as a Home Assistant add-on, with a Home Assistant layer and
many extra commands for the Netherlands and Belgium.

> **Original project:** [agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot). This add-on packages it for Home
> Assistant and adds to it; for the bot's own documentation and all its settings, see the original.

- Settings in the add-on options and on the bot's dashboard, which opens in the Home Assistant sidebar.
- More than 80 commands: weather, traffic, public transport, prices, AEDs, KNMI warnings, route and signal of your message,
  and games for everyone on the mesh (DX Jacht, Mesh RPG, karma, check-in, polls, predictions).
- Answers in the language the sender writes in (Dutch, English, German, French).
- Optional: room server login, notifications, an incoming webhook, a mirror into the MeshCore Chat panel, your repeater's status
  from meshcore-ha, an F1 channel. Everything optional is off until you switch it on.
- Recognises other bots, and the bot name always ends in `|🤖`.

Needs a MeshCore companion radio connected by USB, for example the [Seeed XIAO ESP32S3 + Wio-SX1262 kit](https://www.seeedstudio.com/XIAO-ESP32S3-for-Meshtastic-LoRa-with-3D-Printed-Enclosure-p-6314.html)
with MeshCore companion firmware. The easiest set-up uses the **MeshCore Proxy** add-on from the same repository, so the bot
and the meshcore-ha integration can share the radio.

Read the **Documentation** tab for all options. The full command list is in the
[COMMANDS.md](https://github.com/vipje/Meshcore-bot-for-Home-Assistant/blob/main/COMMANDS.md).
