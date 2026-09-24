# Changelog

## 1.0.0

First public release: [agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot) v1.1.0 as a Home Assistant add-on,
with a Home Assistant layer and extra commands on top.

**Home Assistant**
- Every setting in the add-on options or on the bot's own dashboard (*Plugins* page, one card per command and service); settings
  on the dashboard survive restarts and updates.
- The dashboard in the Home Assistant sidebar (ingress), with extra *Bots* and *Games* pages (click a player to see where the XP comes from; who has predicted the next F1 race). By default it is only reachable
  through the sidebar.
- Works through the MeshCore Proxy add-on, so meshcore-ha and the bot share one radio.
- Optional, each off until switched on: notifications to a room server, channel or DM (and Home Assistant for radio problems), a
  bridge that mirrors replies into the MeshCore Chat panel, an incoming webhook, a heartbeat sensor, the status of your repeater
  from meshcore-ha (`rptr`, with warnings), an F1 channel from the f1_sensor integration.
- **Channel radar** (dashboard page): which hashtag channels are in use around the bot, recognised by channel byte and
  check code against about 200 known names (plus your own on its card), without decrypting anything.
- Export and import of settings and database through `/share/meshcore-bot`, to move the bot to a new installation.
- Room server login with an adjustable re-login interval; as room admin the bot keeps the room's clock right (`clock sync`).

**Commands** (see the command list in the repository README)
- Netherlands and Belgium: traffic jams, road works, public transport, fuel and energy prices, EV chargers, AEDs, KNMI warnings,
  earthquakes, water level, radiation, telecom outages, number plates (RDW), holidays, Buienradar.
- Mesh: route in one line with distance (`pad`), signal with a verdict (`sig`), size of the mesh (`meshkaart`), top users
  (other bots left out), repeaters and commands.
- Community and games: DX Jacht (`dx`), Mesh RPG (`xp`, `badge`), `karma`, daily `checkin`, `prikbord`, `peiling`, `voorspel`,
  reminders by DM (`herinner`), quiz, hangman, polls, facts (`weetje`), quotes, morse.
- `help` pages through all commands, or links to your own command list (help card); `helpall`; admin commands `status`,
  `botlist`, `cleanup`.

**Everywhere**
- Replies in the language the sender writes in (Dutch, English, German, French; optional *AutoLanguage*); Dutch, German and French
  cover all of upstream's texts too.
- Other bots are recognised (robot emoji or the word bot, plus a list on the *Bots* page): no greeting for them, no endless
  replies between bots, not in the rankings.
- In a busy public channel the bot runs no commands but points people to the right channel, with varying texts.
- Contact cleanup that keeps room on the radio, a lasting archive for the games, a small image (13 layers) and a test suite
  that replays the whole build on the upstream source.
