# MeshCore Bot – documentation

This add-on runs the original [agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot) and adds a Home Assistant layer to it.
The original project is the reference for the bot's own commands and settings; this page covers what the add-on adds and how the options map onto it.

## Requirements

- A MeshCore radio with the **companion (USB)** firmware, plugged into the machine that runs Home Assistant.
  Example: the [Seeed XIAO ESP32S3 + Wio-SX1262 kit](https://www.seeedstudio.com/XIAO-ESP32S3-for-Meshtastic-LoRa-with-3D-Printed-Enclosure-p-6314.html) that the author uses. It is sold as a
  Meshtastic kit; flash the MeshCore companion firmware from the
  [MeshCore project](https://github.com/meshcore-dev/MeshCore) onto it first.
- The **MeshCore Proxy** add-on from this repository, so that the bot and meshcore-ha can share that radio.
- Optional, for sensors, telemetry and a chat panel in Home Assistant:
  [meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) and
  [MeshCore Chat](https://github.com/mwolter805/meshcore-ha-chat) (both via HACS).
  The bot works without them; the *Home Assistant chat panel* option needs both.

## Quick start

1. Install and start **MeshCore Proxy** (or choose *Connection → Connection type* `serial` and let
   the bot open the radio itself, then nothing else can use it).
2. Open the **Configuration** tab of this add-on.
3. Set at least:
   - **Bot → Channels to listen on**: the channel names the bot should answer on.
   - **Bot → Admin public keys**: your own 64-character public key (from your MeshCore app).
   - The **Webhook** card on the dashboard's **Plugins** page (off on a new installation): switch it on and set a secret token, otherwise anyone
     on your network can post to the mesh. And **Web viewer → Password**, unless you close the port with *Reachable from the network*.
4. Start the add-on and check the **Log** tab. Send `ping` on one of the channels; the bot answers `Pong!`.
5. **Open Web UI** shows the dashboard, and so does **MeshCore Bot** in the Home Assistant sidebar.

The bot name always gets `|🤖` at the end, so people can see it is a bot.

## Options

### Connection

| Option | Meaning |
|---|---|
| Connection type | `tcp` (through MeshCore Proxy, recommended), `serial` or `ble`. |
| TCP host / port | Where the proxy listens. Default `localhost:5010`. |
| Serial port | Only for `serial`, for example `/dev/ttyACM0`. |
| Bluetooth device name | Only for `ble`. |

### Bot

| Option | Meaning |
|---|---|
| Bot name | Name on the mesh. Do **not** add a robot emoji yourself: `|🤖` is always added at the end automatically (`MeshCore` becomes `MeshCore|🤖`). An emoji you type yourself is removed first, so you never get `🤖|🤖`. |
| Channels to listen on | One channel per entry, exactly as named on your radio. |
| Answer direct messages | Also answers DMs and room server messages. |
| Admin public keys | Keys allowed to use admin commands (`reload`, `advert`, `announce`, ...). Only honoured for real DMs. |
| Delay between message parts | Seconds between the parts of a long reply. |
| Language of the replies | `nl` (default) or `en`. The fixed fallback language of the bot's own replies; Dutch covers about 70% of upstream's texts and falls back to English for the rest. This add-on's own extra commands are fully translated (nl/en/de/fr) and use it too, unless **AutoLanguage** (below) overrides it per message. |
| Minimum time between replies | The bot answers at most once per this many seconds in total (default 4; upstream uses 10). A second command within that time gets no answer. Lower means more airtime. |
| Log level | `DEBUG` shows why a message was ignored. |

### Room server

On the dashboard open **Plugins**, pick **RoomServer Login**, switch it on and fill in the room's 64-character public key and its
password (the guest password is enough to chat). The bot logs in at startup, every hour (*Log in again every*, 15-720
minutes) and after a radio reconnect. From then on everything written in the room is handled like a direct message: commands are
answered in the room.

Things to know:

- **The room's clock must be right.** The bot ignores messages with a timestamp from before it started,
  because it takes those for old cached messages. A room server without GPS or a clock battery can end
  up years in the past after a power loss, and then the bot stays silent without any error. It also
  makes the room keep posts (such as the bot's notifications) that no client ever fetches, because
  they carry an old time. **The bot checks this for you:** after every login it compares the room's
  clock (sent along with the login since firmware 1.10) with its own. Fill in the optional *Room admin
  password* on the card and the bot logs in as admin and runs `clock sync` when the room is more than
  2 minutes behind. Without it, or when the room runs ahead (`clock sync` cannot set a clock back), it
  only says so in the log. By hand: in the room's remote management console run `clock` to check and
  `clock sync` to fix it.
- **Admin from a room.** The bot sees the *room* as the sender, not the person who wrote the message.
  If you add the room's public key to *Admin public keys*, everyone who can write in that room is an
  admin of the bot. Only do that when you are the only one with access (and set a real guest password).
  Otherwise use a direct message for admin commands.

### Weather and units

Country, provider (`openmeteo` worldwide, `noaa` US only) and units for temperature, wind and rain.

### Incoming webhook

Post messages onto the mesh from Home Assistant or a script. Set it up on the dashboard's **Plugins** page, card **Webhook** (switch it on, set the
*secret token*, port and *maximum message length*):

```yaml
rest_command:
  post_to_mesh:
    url: "http://127.0.0.1:8765/webhook"
    method: POST
    content_type: "application/json"
    headers:
      Authorization: !secret mesh_webhook_auth_header   # "Bearer <your secret token>"
    payload: '{{ {"channel": "test", "message": message} | tojson }}'
```

Messages longer than *Maximum message length* are split into several messages.

### Web viewer

The dashboard. Reachable in the Home Assistant sidebar (**MeshCore Bot**, works through Nabu Casa or your own domain too) and with the
**Open Web UI** button (port 8081). Both show the same dashboard. Set a password if port 8081 is reachable from your network. The password
applies in the sidebar as well; if you only use the sidebar, you can leave it empty and block port 8081 in your router or firewall.
**Closing port 8081:** once the sidebar works, switch **Reachable from the network** off. The port is then closed to your network and the
dashboard is only available in the sidebar, so the password can stay empty. Switch it on again to use `http://<host>:8081` (and set a password).
The sidebar uses a fixed port (`ingress_port: 8081`); if you change the viewer port, the sidebar entry stops working until `ingress_port`
in the add-on's `config.yaml` matches.

### Home Assistant chat panel (optional)

The bot talks to the radio itself, so its own replies (in channels, in direct messages and in a room server)
never reach meshcore-ha and would not show up in the *MeshCore Chat* panel. On the dashboard's **Plugins** page open **HomeAssistantBridge**, switch it on and fill in **Home Assistant webhook URL**
(`http://127.0.0.1:8123/api/webhook/meshcore_bot_relay`), and add this automation to Home Assistant; it republishes the reply as the event meshcore-ha itself uses:

```yaml
alias: MeshCore bot relay
triggers:
  - trigger: webhook
    webhook_id: meshcore_bot_relay
    allowed_methods: [POST]
    local_only: true
actions:
  - choose:
      # Replies to a direct message, including everything the bot says in a room server.
      - conditions:
          - condition: template
            value_template: "{{ trigger.json.message_type | default('channel') == 'direct' }}"
        sequence:
          - event: meshcore_message
            event_data:
              entity_id: "{{ trigger.json.entity_id }}"
              sender_name: "{{ trigger.json.sender_name }}"
              receiver_name: "{{ trigger.json.receiver_name }}"
              pubkey_prefix: "{{ trigger.json.pubkey_prefix }}"
              message: "{{ trigger.json.message }}"
              message_type: direct
              outgoing: true
              timestamp: "{{ utcnow().isoformat() }}"
    # Channel replies.
    default:
      - event: meshcore_message
        event_data:
          entity_id: "{{ trigger.json.entity_id }}"
          channel_idx: "{{ trigger.json.channel_idx }}"
          channel: "{{ trigger.json.channel }}"
          sender_name: "{{ trigger.json.sender_name }}"
          message: "{{ trigger.json.message }}"
          message_type: "{{ trigger.json.message_type }}"
          outgoing: true
          timestamp: "{{ utcnow().isoformat() }}"
mode: queued
max: 10
```

Needs the [meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) integration and the
[meshcore_chat](https://github.com/mwolter805/meshcore-ha-chat) panel. **Node prefix** (same card) can stay empty:
it is taken from the radio's public key (the first 6 characters).
Use `127.0.0.1` and not `localhost` in the URL, because the add-on uses host networking and
`localhost` can resolve to IPv6 where Home Assistant does not listen.

### Repeater status from Home Assistant

The [meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) integration polls your repeaters over the radio and publishes what it gets as
Home Assistant sensors (battery, uptime, airtime, noise floor, temperature, neighbours). The **HARepeater** service only **reads** those sensors
from Home Assistant (with the add-on's own permission, `homeassistant_api`, no password). It never sends anything over the radio and never writes
to Home Assistant, so it costs **no airtime**; how fresh the data is depends on how often meshcore-ha asks the repeater.

Switch it on on the dashboard's **Plugins** page, card **HARepeater**, and restart the add-on (services need that). Card settings:

- *Repeaters to follow*: empty = every repeater meshcore-ha knows. Otherwise the first characters of the public key (the 10 characters after
  `meshcore_` in the sensor names). A room server is only followed when you list it. `rptr list` shows what was found.
- *Read Home Assistant every* (default 5 min), *Warn when the battery is low* and *Battery is low below* (default 3600 mV: one message per
  repeater per day through the Notifications card), *Keep the history for* (default 365 days).

It fills two tables in the bot's database, one row per new status reply from a repeater: `repeater_telemetry` (battery, temperature, uptime,
airtime, packet counters, noise floor, signal, neighbour count) and `ha_repeater_neighbors` (the neighbour list of that reply with its SNR).
They are separate from the bot's own neighbour tables on purpose, so nothing upstream changes.

**Airtime advice.** Every status request meshcore-ha sends costs airtime on the mesh, and the neighbour list comes on top. As a rule of thumb
keep it to about one request per hour per repeater (24 a day). Set it in Home Assistant: Settings, Devices and services, MeshCore, Configure,
edit the repeater, *Telemetry Refresh Rate*. The lowest value it allows is 300 seconds, which would be 288 requests a day.

**Warnings.** Besides the low battery, the card can warn (one message per repeater per day at most, through the Notifications card, event
`repeater`): *a repeater restarts* (its uptime dropped), *stops answering* (offline in two reads in a row), *the noise floor jumps* (by the set
number of dB above the usual value of its last readings), *the airtime is high* (above the set percentage) and, off by default, *a neighbour
disappears* (was in the two previous replies, missing now). Each has its own switch on the card. They only read what is stored; nothing is sent.

The command `rptr` (see *Extra commands*) shows the same in the mesh, `rptr accu [24u|7d]` the battery over a period. The service asks Home Assistant for all states, so it needs the
add-on permission `homeassistant_api` (on by default).

### Heartbeat: is the bot alive?

Everything the bot reports about itself comes from the bot, so when the whole add-on is down nothing tells you. The **Heartbeat** service
(card on the Plugins page, off by default, needs an add-on restart) turns it round: every few minutes it writes one sensor in Home Assistant,
`sensor.meshcore_bot_heartbeat` (name is a setting), with the state `online` (or `radio_offline` when the bot runs but has no radio) and the
attributes version, uptime, radio_connected, channels and last_beat. A clean stop sets it to `stopped`. It uses the add-on's own permission
(`homeassistant_api`) and never touches the radio.

Home Assistant then raises the alarm when the sensor has not been updated for a while. Example automation (set the time to a few times the
interval, and the notify service to yours):

```yaml
alias: MeshCore Bot is silent
trigger:
  - platform: template
    value_template: >
      {{ (now() - states.sensor.meshcore_bot_heartbeat.last_updated).total_seconds() > 900
         and states('sensor.meshcore_bot_heartbeat') != 'stopped' }}
action:
  - service: notify.notify
    data:
      message: "MeshCore Bot has not reported for 15 minutes"
```

### Automatic reply language, per sender

**AutoLanguage** (card on the Plugins page, off by default; needs a restart) makes the bot answer in the language someone actually typed,
instead of always the one fixed language from `Bot > Language of the replies` above. It detects the language from the message itself (a short
keyword list for greetings such as "hallo"/"hola"/"danke", and, when the optional `langdetect` package is installed, longer free text too) and,
for the duration of that one reply, swaps in the matching translator — then switches back. No extra airtime: only the text of the reply changes.

It applies to every command, upstream's built-in ones and this add-on's own extra commands alike, and only ever answers in a language a
translation actually exists for (upstream ships `nl`, `en`, `de`, `fr`, `es`, `pl`, `pt`, `ru`, ...; this add-on's own commands currently cover
`nl`/`en`/`de`/`fr`, with English as the silent fallback for anything not yet translated).

Two places keep a *fixed* language on purpose, since their message has no sender to detect a language from: the **F1** service's scheduled
channel posts (its own `Language` setting on the Plugins card) and **info bot**'s DM reply (its own `Language` setting). The `f1` command itself
(`f1`, `f1 stand`, ...) is a normal command and does use AutoLanguage like everything else.

### Formula 1 channel

A channel for Formula 1 that is quiet and predictable, like a news channel, plus a prediction game. It reads the sensors of the
[F1 Sensor](https://github.com/Nicxe/f1_sensor) integration in Home Assistant (read-only, with the add-on's own permission) and needs no airtime for that.

**Set up (once)**
1. In the MeshCore app add the hashtag channel `#f1` to your radio (the bot does not touch the radio's channels).
2. On the dashboard's **Plugins** page open the **F1** card, check *Channel for the F1 posts*, switch it on and restart the add-on.
3. Do **not** add `#f1` to *Bot, Channels to listen on*. The `f1` command has its own channel list (`#f1`, on its card), and that is what makes
   `f1` work there while `ping`, `wx` and the other commands stay out of the channel.

**What the bot posts** (all on the F1 card):
- every day at 12:00 the countdown, *"F1: nog 12 dagen tot de GP Italië (Monza), zo 4 okt 15:00"*, until 3 days before the race;
- then, once, the race weekend with all session times;
- a reminder 60 minutes before qualifying, the sprint and the race;
- after the race (and the sprint) the top 10 and the winner, then the championship top 5 and the constructors' top 3, and the result of the game;
- during a session (*Live updates*): the start, the top five at 25, 50 and 75% of the race, a safety car or red flag, and the qualifying result.
  This needs the live sensors of f1_sensor; when they are unavailable nothing is posted. At most 8 live posts per race.

Nothing is ever posted twice: what was posted is remembered across restarts. That is about 14 messages per race weekend and one a day in between,
on average less than two a day (P2000 sends 25 to 30), about 1.5 seconds of airtime per message on a 62.5 kHz / SF8 radio. If sending fails (for
instance because the channel is not on the radio) the bot waits 15 minutes and tries again, and logs one warning.

**Commands**, in `#f1` and by direct message: `f1` (next race, with all times in a race week), `f1 stand`, `f1 team`, `f1 uitslag`, `f1 nu` (the live
session) and the game below.

**Prediction game.** Pick the winner of the next race with `f1 voorspel VER` (the three letters of the driver). **This only works by direct message**:
a channel message only carries a display name, which anyone could copy, while a direct message carries your public key, which cannot be faked. The
bot stores that key (never shown) so nobody can vote for someone else. You can change your pick until the first qualifying session of the weekend
starts. After the race: winner right = 5 points, a pick that finished second or third = 2, otherwise 0. `f1 spel` shows the standings (and, by DM,
your own points and pick). The names in the standings are the names people had when they last played.

### Contacts and map

The radio has a fixed number of contact slots (350 on the Seeed XIAO ESP32S3 firmware). The bot does **not**
keep its map in those slots: every node it hears is stored in the bot's own database, and the dashboard map
is drawn from that database. Removing a contact from the radio therefore does not remove it from the map.
Only the delete buttons and the data-purge tool in the dashboard itself remove map data.

| Option | Meaning |
|---|---|
| Contact management | `device` (recommended): the radio adds contacts and overwrites the oldest one that is not a favourite. `bot`: the bot adds contacts. `false`: manual. |
| Never remove starred contacts | Contacts you star in the dashboard are never removed from the radio by the bot (auto-purge, stale-contact cleanup and manual purge all skip them) and get the favourite mark on the radio within 30 minutes, so the firmware's own "overwrite the oldest" policy keeps them too. |
| Keep favourites set in the MeshCore app | The original bot clears the favourite mark of every contact that is not on its protected list, about 3 minutes after each start. Leave this on to keep the stars you set in the app. |

The cleanups and the backup are set on the dashboard:

- **Plugins → ContactCleanup**: *Trim the contact list* (when the radio holds *Clean up when* contacts or more, checked every 30 minutes, the
  oldest unused ones are removed until *Clean up down to* is reached; repeaters that went quiet go first), *Never remove contacts active within*
  (days), and the weekly removal of silent contacts (*Repeaters silent for more than* 14 days, *Other contacts silent for more than* 30 days,
  0 = never). Switch the plugin on to use them.
- **Configuration → Database Backup**: the daily database backup (map, contact history, statistics), how many to keep, and the time. Stored in
  `/data/backups`, which Home Assistant backups of this add-on include. A new installation starts with a daily backup at 02:00 keeping 7.

Both cleanups **never remove**: contacts starred in the dashboard, favourites on the radio, the room server the bot logs in
to, admins and the bot's other protected keys, and contacts with no known last-seen time. Everything removed stays in the
bot database and therefore on the dashboard map.

You can also run them by hand with the admin command `cleanup` (see *Extra commands*).

**More contact slots** is a firmware setting, not a bot setting: `MAX_CONTACTS` is compiled into the radio firmware.
To get more (for example 500) you build the MeshCore companion firmware yourself with a higher `-D MAX_CONTACTS=`
in the `platformio.ini` of your board, and flash it. The bot follows automatically, because it reads the limit from
the radio. The firmware reports the limit in one byte (`MAX_CONTACTS / 2`), so 510 is the ceiling. Every extra contact
costs roughly 190 bytes of RAM on the radio. With the default "overwrite the oldest non-favourite" policy a full list
is not a problem in daily use, so this is rarely needed.

### Notifications

The bot can tell you when something goes wrong, so you do not have to read the log. It watches its own log and
sends a short message to a **room server**, a **(private) channel** or a **direct message**. You choose with
*Send notifications to* and *Room key, channel or contact* on the dashboard's **Plugins → Notifications** card: for a room, leave the
target empty to use the room the bot logs in to. Every notification setting is on that card.

| Event | Reported when |
|---|---|
| `startup` | The bot (re)started; includes the add-on version, radio state and number of contacts. |
| `radio` | The radio is offline, in a zombie state or does not reconnect, and again when it is back. |
| `room_login` | Logging in to the room server failed. |
| `send_failed` | A message was not delivered after all retries (for example a DM without ACK). |
| `contacts_full` | The contact list is full or nearly full (at most once a day). |
| `ha_bridge` | The link to the Home Assistant chat panel fails. |
| `command_error` | A command crashed. Only the command name is reported, never the text people typed. |
| `admin_command` | An admin command was used somewhere other than where the notifications go, and by whom. A command you type in the log room itself is not repeated there: you already see the reply. |
| `repeater` | The battery of a repeater is low (see *Repeater status from Home Assistant*). Switched on by *Warn when the battery is low* on the HARepeater card, so it also works when this list was saved before the event existed. |
| `error` | Any other error (or, with *Report other problems from* `WARNING`, warnings too). |

Airtime on a mesh is scarce, so the messages are kept small:

- the same message is sent at most once per *Same message at most once per (minutes)*; repeats are counted and
  mentioned with the next message;
- problems that happen within *Wait to combine messages* seconds share one message;
- a message is at most about 140 bytes and at most 3 messages are sent per batch (`(+N meer)` says how many were left out);
- passwords, tokens and long keys are masked, and other people's messages are never included.

A notification that itself fails to send is only written to the normal log, so a broken destination can never cause a loop.
Messages start with `⚠` (problem) or `ℹ` (information) and never with a command word, so the bot does not react to its own messages
if the destination is a room it is logged in to.

**Radio problems also go to Home Assistant.** When the radio is down the mesh cannot tell you, so with
*Also tell Home Assistant about radio problems* the bot creates a persistent notification, and with *Home Assistant notify service*
(for example `notify.mobile_app_myphone`) a push message on your phone. This uses the Home Assistant API that the add-on
is allowed to reach; no token has to be filled in.

**Daily summary.** One message a day at the chosen time with uptime, number of commands, errors and warnings, contacts and radio state.

**On request.** The admin command `status` (in the room or as a DM) shows the same without waiting: uptime, radio, contacts,
counters and the most recent problem. It works even when notifications are switched off.

### Public channel

For a busy channel where the bot should listen but not run commands, typically the public channel. Everything is set on the dashboard's
**Plugins** page. The channel is **not** added to *Bot, Channels to listen on*, so no command runs there.

- **Tells people where commands work** (card **ChannelHint**: switch it on, fill in *Channels that get a hint* and *Channels where commands do
  work*). When someone types a command word that has a hint switched on, the bot answers once with a friendly pointer to the channels you
  list, for example *"We helpen je heel graag verder in #bot of #test"*. At most one hint per channel per *At most one hint per channel
  every* seconds and one per person every 10 minutes, so it cannot flood the channel. Changes on this card work within about 30 seconds.
  **Which commands give a hint is set per plugin**: on **Plugins**, pick a command and set **Hint in the public channel**:
  - *Off*: no hint (the default for every command);
  - *When the command word is typed alone*: `help`, `Test?`, `!ping` or `@[bot] help` get a hint, anything longer does not;
  - *Alone or with arguments*: also `wx amsterdam`, as many words after the command as its usage shows.

  **Variation:** put several texts in *Hint text*, separated by `||`, for example
  `We helpen je heel graag verder in {channels} || Voor commando's en tests ben je welkom in {channels}`. The bot picks one at random and
  never the same one twice in a row, so someone who types `test` three times does not get the same answer three times.
  Out of the box `ping`, `test` and `help` are set to *alone*; all other commands are off, because people should not be tempted to
  use them in the public channel. A sentence such as "ik help wel even mee" or "heb jij een test voor mij" never gets a hint.
- **Greets new people** (card **greeter**, a command: switch it on, set *Channels* to the public channel and the greeting text). After
  switching it on the bot first listens for *rollout_days* (default 7) and marks everyone who is active as already greeted, so a busy
  channel is not greeted all at once. In that card's *Other config values*: `dead_air_delay_seconds` (wait before greeting, seconds) and
  `defer_to_human_greeting` (skip the greeting if someone already welcomed the newcomer by name). **The greeter never greets other bots.**
- **Stays quiet when another bot answers.** If another bot serves your region, both would answer the same message. Bots are
  recognised by the robot emoji in their name (`Name|🤖`, which this add-on always adds to its own bot name) or by the word
  "bot" in it (`DX1ABC-BOT`, `Echobot`, `BE-XYZ-Town-Bot`, `BotAmsterdam`; any case, but not when a letter follows, so `Botond`
  and `Abbott` stay people). Both lists are fields on the **ChannelHint** card, next to *Do not answer other bots* (on by default: commands
  typed by another bot in a channel are ignored, so two bots cannot answer each other for ever). Single names can be forced either way on the dashboard's
  **Bots** page (tick boxes, top bar) or with the admin command `botlist` (see *Extra commands*). With *Wait for other bots first* on the
  card above 0, the bot waits that many seconds plus a random extra of up to 8 seconds, so two bots do not answer at the same moment. If
  another bot has spoken in that channel in the meantime, or was already active there recently, the hint is not sent.
- **A weekly announcement** is no longer an add-on option. Make it an ordinary scheduled message on the dashboard's **Schedule** page:
  channel, day, time and text (at most 130 bytes per message). It is not coordinated with other bots: if another bot in your region also
  posts one, choose a different day or time. Set *Bot, Time zone* if the bot should not use the system time zone.

Use the channel names exactly as they are named on your radio.

### Where a command may be used

Every command has its own channel list. In the bot's dashboard open **Plugins**, pick a command and fill in **Channels**
(comma-separated). Blank means the channels the bot listens on; DMs always work. If someone uses the command in another channel,
the bot answers *"Dat commando werkt hier niet. We helpen je graag verder in: #bot"* with the channels you listed, if that command has its *Hint* setting on.

**Your dashboard settings are kept.** The add-on rewrites `config.ini` at every start, but only the settings that the add-on
options manage (for example weather units and admins). The settings of **Notifications**, **ContactCleanup**, **RoomServer Login**,
**HomeAssistantBridge**, **Webhook**, **ChannelHint** and **greeter** live only on the Plugins page.
Changes to a command's card (such as **greeter**) and to **ChannelHint** work within seconds; the cards of the other services
(Notifications, ContactCleanup, RoomServer Login, HomeAssistantBridge, Webhook) take effect after you restart the add-on. Everything else, such as a command's *Channels* list or
other values you change on the dashboard's Plugins page, stays as you set it. If you change something on the dashboard that the
add-on options also manage, the option wins at the next start. When you switch an option off or remove a list entry, the setting
it produced is removed again, so it falls back to the bot's default.

### Commands

You do not get a switch per command. Two lists do the same job:

- **Extra commands to enable**: commands that are off by default (`airplanes`, `worldcup`).
- **Commands to disable**: command names to switch off, for example `dadjoke`, `quiz`, `hangman`.
  The bot then answers that the command is disabled. This works for commands that read an `enabled`
  setting in their own `[Name_Command]` section, which is the case for the standard commands and
  the extra commands below.

**RSS/API feeds** must be enabled for `feed subscribe` to fetch anything;
*Ignore feed items older than* stops a new feed from flooding a channel with its backlog.

### Hiding names from `topu`

The `topu` (top users) command leaves other bots out by itself: the same rules as the **Bots** page (a robot emoji or the word bot in the
name, plus the names marked there) and the bot itself. Switch: **Leave out bots** on the **topusers** card (Plugins), on by default.
It can also leave out names you choose, for example a room server that shows up with your own messages: fill in **Never show these names**
on the same card (comma-separated, not case sensitive). Both are kept across restarts. The dashboard's own Busiest users panel is not affected.

### Community commands and games

Commands for everyone on the mesh. Each has a card on the Plugins page with an on/off switch; some have a setting or two.

- **DX Jacht** (`dx`): the record for the message that came in over the most hops, this week, this month and ever. `dx top [week|maand|ooit]`
  is the ranking, `dx ik` / `dx <name>` someone's own records.
- **Mesh RPG** (`xp`, `badge`): taking part earns XP: 1 per message (max 20 a day), 2 per bot command (max 10 a day), 5 per check-in,
  10 per karma point received, 5 per hop of your best DX (counted up to 10 hops, so at most 50). Levels need 50, 150, 300, 500, ... XP, with titles from *Nieuwkomer* to
  *Mesh-legende*. `xp top [week]` is the ranking; `badge` shows milestones (100/1000 messages, 30/100 active days, 3/6 hops, check-in
  streak 7/30, 10 karma, level 5/10).
- **The archive behind them.** The bot's own statistics last only 7 days (`Stats_Command.data_retention_days`). The **Community** service
  (card, on by default) copies a summary per person per day into the bot's database every 10 minutes (messages, commands, best hop count), so
  records and XP last. It only reads; it never sends anything. XP starts counting from the day the add-on is installed (plus the last 7 days of the bot's statistics).
- **Reminders** (`herinner`, direct message only): `herinner 30m <text>`, `herinner 18:30 <text>` (also `2u`, `1d`), `herinner lijst`,
  `herinner weg <nr>`. At most 3 open, at most 7 days ahead. The **Reminders** service (card, on by default) sends them back to you as a direct
  message at that time, and keeps them across restarts. The language of that message is a setting on its card.
- **Prediction game for any question** (`voorspel`): someone asks a question by direct message (`voorspel nieuw Droog zaterdag? | ja | nee`),
  people answer by direct message (`voorspel 1`), the one who asked closes it (`voorspel sluit`) and gives the answer (`voorspel uitslag 1`):
  1 point for everyone who had it. `voorspel` and `voorspel stand` also work in a channel. One open question at a time. Like the F1 game it
  goes by public key, so nobody can answer for someone else.
- People are recognised by the name they use on the mesh (a channel message carries nothing else). Rankings leave bots out.
- **Channel radar:** the dashboard's *Channel radar* page shows which hashtag channels are in use around the bot: per
  channel the group messages of today, the last 7 and 30 days and when it was last heard, and whether that channel is on
  your radio. A group message starts with a channel byte and a 2-byte check code; the radar compares them with the keys of
  about 200 common names and tens of thousands of generated variants such as `mesh-zl` or `maastricht-chat` (a hashtag
  channel's key follows from its name), and only lists a channel when both match; a generated name only from 2 messages.
  When the list of names changes, the days still in the packet log (about 3) are counted again. It
  never decrypts anything and sends nothing. Messages on channels it cannot name (private channels, unknown names) are
  counted by channel byte. Add names you suspect on the **ChannelRadar** card (on by default).
- **Games page:** the dashboard has a *Games* menu item (next to *Bots*) with all standings in one place: Mesh RPG, DX Jacht, karma,
  check-in streaks, the open `voorspel` question and the F1 prediction game. Read-only, refreshes every minute, bots left out.
  Click a name in Mesh RPG to unfold where that person's XP comes from (messages, commands, check-ins, karma, best DX) and
  their badges. Under the F1 standings you see who has already predicted the next race (names only; the picks stay hidden
  until the race is scored, and only then do points appear).

| Command | What it does |
|---|---|
| `pad` | The route of your message in one line: hops, distance and repeater names, e.g. `3 hops · 42 km · Horsth·→YAGI?→Wester·` (`?` = best guess). The long version is `path`. |
| `sig` | SNR, RSSI and hops of your message with a verdict (goed / redelijk / zwak). With hops the numbers are about the last repeater. |
| `meshkaart` (`nodes`) | How many nodes, repeaters and rooms the bot heard in 24 hours, 7 days and ever. The map is the dashboard's Mesh page. |
| `karma <name>`, `karma`, `karma top` (`topkarma`) | Thank someone with a point. Not yourself, not a bot, only names heard in the last 30 days; one point per person per day from the same giver, at most 3 a day (setting). |
| `checkin` (`meld`), `checkin top` | Daily check-in with a streak counter, days in local time. |
| `prikbord`, `prikbord <text>`, `prikbord <nr>`, `prikbord weg <nr>` | Notice board: short notes (max 90 bytes) that stay 7 days (setting), at most 2 per person (setting). |
| `noodnummers` (`nood`) | 112 first, then the region's own numbers from the card (field *Numbers for this region*), or the national ones. Asked in a channel, the answer comes as a direct message (card: *Answer by direct message*, on by default; in the channel after all when the DM cannot be sent). |
| `weetje` | A Dutch did-you-know; the whole list before one comes back. |
| `peiling [15m\|2u\|1d] <question> \| a \| b ...` | Multiple-choice poll (2-5 choices) on a channel, vote with `kies <nr>`, `peiling uitslag`, `peiling stop`. The yes/no version stays `stem`. |
| `buien [place]` | Rain in the next 2 hours, one character per 10 minutes (Buienradar, NL/BE). Without a place: your position if the bot knows it, else the bot's. |

### Advanced

- **Keyword replies**: one `keyword = "reply"` per entry. Placeholders: `{sender}`, `{connection_info}`,
  `{timestamp}`, `{phrase_part}`.
- **Extra config lines**: one `Section.key = value` per entry, applied last, so it wins over every
  other option. Any setting of the bot can be set this way, see
  [config.ini.example](https://github.com/agessaman/meshcore-bot/blob/main/config.ini.example).
  Example: `Sports_Command.enabled = true`.
- **Channel check**: the bot checks after every start (after 30, 60 and 120 s) and then every hour that it knows all channels from
  **Bot > Channels** and the ones it saw last time, and asks the radio again for any that are missing. Change the interval with the
  extra config line `Connection.channel_recheck_minutes = 60` (`0` = only the three startup checks). Look for `Channel check:` in the log.

The add-on rebuilds the bot's `config.ini` from these options on every start. Changes made in the
bot's own web viewer settings pages are therefore not kept; use the options here.

## Extra commands

Added by this add-on on top of the bot's own commands. Most use open data for the Netherlands or Belgium
and need internet.

| Command | What it does |
|---|---|
| `aed <place>` | Nearest AEDs. Asked in a channel, the answer comes as a direct message (card: *Answer by direct message*, on by default; in the channel after all when the DM cannot be sent). |
| `cleanup [stale] [now]` | Admin only. Shows what a contact cleanup would remove; `cleanup now` does it. `cleanup stale` is the same for silent contacts. |
| `status` | Admin only. Uptime, radio state, contacts, counters and the most recent problem. |
| `botlist [add\|not\|del\|check] [name]` | Admin only. The dashboard's **Bots** page edits the same lists with tick boxes. Overrules the automatic bot recognition for single names: `botlist add Echobot` always counts as a bot, `botlist not Talbot` never, `botlist del` removes the name from both lists, `botlist check DX1ABC-BOT` says what the bot thinks and why. Without arguments it shows the lists. Kept in the bot's database, so it survives restarts. |
| `beving` | Recent earthquakes in and around the Netherlands (KNMI) |
| `energieprijs` | Current dynamic electricity price (EnergyZero) |
| `feestdag` | Public holidays NL/BE |
| `file <place>` | Traffic jams and incidents near a place |
| `hangman`, `quiz`, `poll` (`stem`) | Games and channel polls |
| `f1 [stand\|team\|uitslag\|nu\|voorspel <code>\|spel]` | Formula 1: next race, standings, last result, live session, and the prediction game (`voorspel` by direct message only). Works in the `#f1` channel and by DM; see *Formula 1 channel*. |
| `rptr [buren\|accu [24u\|7d]\|list\|name]` | Status of your repeater from Home Assistant (battery, uptime, airtime, neighbours; costs no airtime). `rptr accu 7d` shows the battery over a period: now, lowest, highest and the trend, with an estimate when it will be low. |
| `helpall [page]` | Complete command list, one page at a time |
| `help` | A few commands and how to get more. With *Link to the full command list* filled in on the help card (Plugins), a bare `help` answers with that link instead, for example a page with every command and what it does. |
| `info bot` | Direct message only. What this bot is and what you need for your own: Home Assistant, a MeshCore USB radio and the add-ons. The GitHub link, the language (nl or en) and one extra line about yourself are settings on the **info** card (Plugins). Without a link the link part is left out. |
| `kenteken <plate>` | Number plate check (RDW open data). Dutch plates only: a Belgian or German plate gets the answer that there is no free source for it. |
| `laadpaal <place>` | Nearest EV chargers |
| `morse <text>` | Text ⇄ Morse code |
| `ov <stop>` | Next public transport departures |
| `quote` | Random quote |
| `storing <provider>` | Telecom provider outage status |
| `straling <place>` | Indicative radiation level |
| `tanken` | National average fuel prices today (CBS) |
| `topc`, `topr`, `topu` | Top commands, repeaters, users |
| `uptime` | How long the bot has been running |
| `waterstand` | Water level of the Maas |
| `weerwaarschuwing` | Current official KNMI weather warning |
| `wegwerk <place>` | Roadworks near a place |
| `whois <name or key>` | Contact card of a known node |
| `dx`, `xp`, `badge`, `herinner`, `voorspel`, `pad`, `sig`, `meshkaart`, `karma`, `checkin`, `prikbord`, `noodnummers`, `weetje`, `peiling`, `buien` | See *Community commands and games* above |

## Moving the bot (export and import)

Settings made on the dashboard, the games, the archive and the rest of the bot's database live inside the add-on. To take
them to a new installation (another Home Assistant, or this add-on installed from another repository) use the
`/share/meshcore-bot` folder (reachable with the Samba or SSH add-on, or the File editor with *Enforce basepath* off):

1. **Export:** create an empty file `/share/meshcore-bot/EXPORT` and restart the add-on. At the next start the bot copies
   `config.ini`, its database, `generated_keys.json` and the add-on options to `/share/meshcore-bot/export/<date-time>/`
   and removes `EXPORT` again. The log says `export ready in ...`.
2. Install the add-on on the new installation, but **do not start it yet**.
3. **Import:** copy the files of that export folder into `/share/meshcore-bot/import/` (on the new machine), then start
   the add-on. It imports only when it has no settings of its own yet, restores the add-on options (the Configuration tab
   shows them after the next start) and renames the folder to `import-done-<date-time>`.
4. Stop the old add-on, so two bots do not use the same radio or name.

The export holds your passwords and keys (room, webhook, dashboard): keep it to yourself. The radio's own identity lives
on the radio, not in the export. The add-on needs `share` and `hassio_api` access only for this.

## Troubleshooting

| Problem | Try |
|---|---|
| The bot does not answer in the room but the log shows `Received DM from <room key>` | The room's clock is wrong, see *Room server* above. |
| `RoomServer_Login: ... mislukt` in the log | Wrong password, wrong public key or the room is out of range. |
| Bot cannot connect | Is MeshCore Proxy running? Check *Connection* (tcp, localhost, 5010). |
| `rptr` says the link is off, or there is no data | Switch on **HARepeater** on the Plugins page and restart the add-on. In the log look for `HARepeater:`: *geen toegang* means the add-on lacks `homeassistant_api`; no repeaters means meshcore-ha has no repeater sensors yet (add the repeater in its configuration). |
| A new option is missing after an update | Rebuild the add-on, and if it is still missing restart the Supervisor (Supervisor caches the option schema). |
| Nothing happens and the log is silent | Set *Bot → Log level* to `DEBUG` and try again. |
| Replies are not in the MeshCore Chat panel | Check the automation above and *Home Assistant → Webhook URL*. |

## Support

Issues with this add-on: the issue tracker of this repository. Issues with the bot itself:
[agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot/issues).
