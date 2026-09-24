# Installation, step by step

*[Nederlands](INSTALL.nl.md) · back to the [README](README.md)*

This guide takes you from an empty Home Assistant to a bot that answers on the mesh. It assumes your radio already runs
the MeshCore **companion (USB)** firmware. Every option is also explained in the **Documentation** tab of each add-on.

## 1. Before you start

- **Home Assistant OS or Supervised.** Add-ons need the Supervisor; a Home Assistant *Container* or *Core* installation
  cannot run them.
- **The radio is plugged in** by USB into the machine that runs Home Assistant.
- **Your own public key** (64 characters). You find it in your MeshCore app, in the settings of your own node. With it,
  the bot knows who its admin is.
- **Which channels will the bot use?** Ask around in your region first which channels already have a bot (see
  [Sharing the mesh with other bots](README.md#sharing-the-mesh-with-other-bots)). A common choice is a `#bot` channel for
  commands and `#test` for tests; leave the public channel to people.

## 2. Add the repository

1. **Settings → Add-ons → Add-on Store**.
2. Top right **⋮ → Repositories**, paste `https://github.com/vipje/Meshcore-bot-for-HA` and click **Add**.
3. Close the window. **MeshCore Proxy** and **MeshCore Bot** now appear in the store (reload the page if they do not).

## 3. MeshCore Proxy

Only one program at a time can open the USB radio. The proxy opens it once and shares it over TCP (port 5010) with the
bot and, if you use it, meshcore-ha.

1. Open **MeshCore Proxy** and click **Install**.
2. Tab **Configuration**, **Serial port**: the path of your radio. `/dev/ttyACM0` is common; a
   `/dev/serial/by-id/usb-...` path is better, because it does not change when you plug in other USB devices. Not sure?
   Just start the add-on: if the port is not found, the **Log** tab lists the paths that exist.
3. Tab **Info**: switch on **Start on boot** and **Watchdog**, then click **Start**.
4. The **Log** tab shows `Luistert op 0.0.0.0:5010` ("listening on"; the proxy logs in Dutch). The proxy is ready.

**Using meshcore-ha too?** Set it to connection type **TCP**, host `localhost`, port `5010`, instead of the USB port.

## 4. MeshCore Bot

1. Open **MeshCore Bot** and click **Install**. Home Assistant builds the add-on on your own machine; that takes a few minutes.
2. Tab **Configuration**. The connection is already right for the proxy (`tcp`, `localhost`, `5010`). Fill in the **Bot** part:

   | Option | What to fill in |
   |---|---|
   | Bot name | The name on the mesh, for example your town. Do not add an emoji: `|🤖` is added automatically. |
   | Channels to listen on | One channel per line, exactly as named on the radio, for example `#bot` and `#test`. |
   | Admin public keys | Your own 64-character public key (step 1). |
   | Language of the replies | `nl` or `en`. |
   | Time zone | For example `Europe/Amsterdam`; empty = the system time zone. |

   The rest can stay as it is. Click **Save**.
3. Tab **Info**: switch on **Start on boot**, **Watchdog** and **Show in sidebar**, then click **Start**.
4. The **Log** tab shows the bot connecting to the proxy and loading its commands.

**The channels must also exist on the radio.** The bot can only hear channels the radio knows. Add them on the
dashboard (next step), page **Radio**, section channels. A hashtag channel such as `#bot` only needs its name. After adding a
channel, restart the bot add-on once so it picks it up.

## 5. First test

From your phone, in one of the bot's channels:

- `ping` → the bot answers `Pong!`
- `test` → the bot answers with how it received your message (path, signal)
- `help` → a link to the command list

A direct message to the bot works too. No answer? See [Troubleshooting](#9-troubleshooting).

## 6. The dashboard

Click **MeshCore Bot** in the Home Assistant sidebar. The most important pages:

| Page | What you do there |
|---|---|
| Dashboard | Status of the bot and the radio. |
| Mesh / Contacts | The nodes the bot hears, on a map and in a list. |
| Radio | Radio settings and the channels on the radio. |
| **Plugins** | A card per command and per service: switch it on or off and set its options. |
| Bots | Which names count as bots (for games, rankings and "never answer another bot"). |
| Games | Standings of all games, without bots. |
| Radar | Which channels are active in your area (counted without decrypting anything). |
| Schedule | Messages the bot posts at a fixed time. |

On **Plugins**, cards of **commands** take effect at once. Cards of **services** need a restart of the add-on; the card says so.

## 7. What to switch on

A new installation starts quiet: everything that needs your own setup is off. Worth a look:

| Card | What it does |
|---|---|
| **ChannelHint** | Makes the public channel a hint channel: no commands there, just a short pointer to your bot channels. Set *Channels that get a hint* (for example `Public`) and *Channels where commands do work* (`#bot`, `#test`). |
| **greeter** | Welcomes new people in a channel. It first listens for 7 days, so an active channel is not greeted all at once. |
| **RoomServer Login** | Logs the bot into your room server, so commands work there too and notifications can go there. |
| **Notifications** | Messages about the bot itself (started, radio lost, ...) to a room, channel or DM. |
| **Webhook** | Lets Home Assistant post messages on the mesh. **Set a secret token first.** |
| Community, Reminders, ChannelRadar | Games, `herinner` (reminders) and the radar. On by default. |

With **meshcore-ha**: **HARepeater** (status of your repeater, `rptr`) and **HomeAssistantBridge** (the bot's replies in the
MeshCore Chat panel). With the HACS integration *f1_sensor*: **F1** (the F1 channel and prediction game). The add-on's
**Documentation** tab explains each of them.

## 8. Security

- The dashboard is only reachable through the Home Assistant sidebar (*Reachable from the network* is off). Leave it that
  way; if you do open port 8081, set a password under **Web viewer**.
- Switch on the **Webhook** only with a secret token.
- Only put keys you trust under *Admin public keys*. Admin commands only work in real direct messages.

## 9. Troubleshooting

| Problem | Try |
|---|---|
| The proxy cannot find the radio | Check the list of paths in the proxy log; is another add-on or integration still using the USB port? |
| The bot does not connect | Is the proxy running? Start the proxy first, then the bot. |
| No answer in a channel | Is the channel in *Channels to listen on* **and** on the radio? Restart the bot after adding a channel. |
| No answer at all | Set *Bot → Log level* to `DEBUG`, send `ping` again and read the log. |
| No answer in the room | The room's clock may be wrong; see *Room server* in the Documentation tab. |

## 10. Moving to another installation

Your settings, games and database can go with you to a new Home Assistant: put an empty file `EXPORT` in
`/share/meshcore-bot/`, restart the bot, and copy the files from `/share/meshcore-bot/export/...` to
`/share/meshcore-bot/import/` on the new installation before its first start. The steps are in the Documentation tab,
*Moving the bot*.

More in the **Documentation** tab of the bot. Questions about these add-ons:
[issues of this repository](https://github.com/vipje/Meshcore-bot-for-HA/issues).
