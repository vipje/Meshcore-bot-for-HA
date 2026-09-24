# MeshCore-bot voor Home Assistant

*[English](README.md)*

> **Gebaseerd op [agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot)** van Adam Gessaman en anderen (MIT).
> Deze repository maakt daar Home Assistant add-ons van en voegt er eigen commando's, spellen en een Home Assistant-laag
> aan toe. Het is geen officieel onderdeel van dat project; zie [Met dank aan](#met-dank-aan).

Home Assistant add-ons voor een MeshCore-mesh: een **bot** met ruim 80 commando's (weer, verkeer, OV, hulpnummers,
spellen, F1, ...) en een **proxy** zodat de bot en de [meshcore-ha](https://github.com/meshcore-dev/meshcore-ha)-integratie
dezelfde USB-radio kunnen delen. Veel extra commando's gebruiken Nederlandse en Belgische open data; de bot antwoordt in
het Nederlands, Engels, Duits of Frans.

| Add-on | Wat het doet |
|---|---|
| [MeshCore Proxy](meshcore-proxy/) | Deelt één USB-radio via TCP, zodat meshcore-ha en de bot hem tegelijk kunnen gebruiken. |
| [MeshCore Bot](meshcore-bot/) | De [agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot) als add-on: alle instellingen in Home Assistant en op het dashboard, een dashboard in de HA-zijbalk, room server, webhook, meldingen en veel extra commando's en spellen. |

```
                    ┌──────────────┐
  USB-radio ──────► │ MeshCore     │ ◄────── meshcore-ha (integratie, optioneel)
                    │ Proxy :5010  │ ◄────── MeshCore Bot (add-on)
                    └──────────────┘
```

## Wat heb je nodig

- **Home Assistant OS of Supervised** (add-ons hebben de Supervisor nodig).
- **Een MeshCore-radio met companion (USB) firmware**, via USB aan de computer waarop Home Assistant draait, met een
  antenne voor jouw band (868 MHz in Europa). Bijvoorbeeld de
  [Seeed XIAO ESP32S3 + Wio-SX1262](https://www.seeedstudio.com/XIAO-ESP32S3-for-Meshtastic-LoRa-with-3D-Printed-Enclosure-p-6314.html)
  met firmware van het [MeshCore-project](https://github.com/meshcore-dev/MeshCore).
- **Optioneel**, voor extra functies (standaard uit, per onderdeel aan te zetten op het dashboard, pagina *Plugins*):
  [meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) (status van je repeater, `rptr`),
  de HACS-integratie *f1_sensor* (het F1-kanaal en voorspellingsspel), een eigen room server (meldingen en chatten via de room).

## Installeren in het kort

Klik op de knop om deze repository aan je Home Assistant toe te voegen, of volg stap 1:

[![Add the repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fvipje%2FMeshcore-bot-for-Home-Assistant)

1. In Home Assistant: **Instellingen → Add-ons → Add-on Store → ⋮ → Repositories**, voeg toe:
   `https://github.com/vipje/Meshcore-bot-for-Home-Assistant`.
2. Installeer **MeshCore Proxy**, kies bij *Seriële poort* je radio en start hem.
3. Installeer **MeshCore Bot**, vul minstens de botnaam, de kanalen en je eigen *Admin-publieke sleutel* in en start hem.
4. Open het dashboard via de HA-zijbalk en zet op de pagina *Plugins* aan wat je wilt gebruiken.

**Stap voor stap, met uitleg: [INSTALL.nl.md](INSTALL.nl.md).** Alle opties staan in het tabblad **Documentatie** van elke add-on (Engels).

## Schermafbeeldingen

*Plugins*: een kaart per commando en service (hier de verwijzing in het openbare kanaal)

![Plugins](docs/images/plugins.png)

*Games*: alle standen, zonder bots (namen hier onleesbaar gemaakt)

![Games](docs/images/games.png)

*Channel radar*: welke hashtag-kanalen er rond de bot actief zijn

![Channel radar](docs/images/radar.png)

## De mesh delen met andere bots

Een mesh is gedeelde zendtijd. Als meerdere bots dezelfde regio bedienen, mogen ze de mensen en elkaar niet overstemmen.
Daar is deze add-on op gebouwd:

- **Herkenbaar.** De botnaam eindigt altijd op `|🤖` (`MeshCore` wordt `MeshCore|🤖`), zodat iedereen ziet dat een bericht van een bot komt.
- **Herkent andere bots** aan de robot-emoji of het woord "bot" in hun naam (`Naam|🤖`, `DX1ABC-BOT`, `Echobot`;
  `Botond` of `Abbott` blijven mensen). Namen kun je ook zelf aanwijzen op de pagina *Bots* van het dashboard.
- **Antwoordt nooit een andere bot.** Commando's die een andere bot in een kanaal typt, worden genegeerd, zodat twee bots
  niet eindeloos op elkaar reageren. De begroeter begroet geen bots, en bots doen niet mee in ranglijsten en spellen.
- **Laat het openbare kanaal aan de mensen.** Een druk kanaal kun je een "verwijskanaal" maken (kaart *ChannelHint*):
  daar werken geen commando's. Wie er toch een commando typt, krijgt een korte verwijzing naar je botkanalen. De bot
  wacht eerst 15 tot 23 seconden en zegt niets als een andere bot al gereageerd heeft.
- **Antwoordt hooguit één keer per 4 seconden** in totaal, en knipt lange antwoorden op met een pauze.

Wat hij **niet** doet: luisteren twee bots op hetzelfde commandokanaal, dan antwoorden ze allebei. Vraag daarom vooraf in
je regio welke kanalen al een bot hebben, en geef je bot eigen kanalen (bijvoorbeeld `#bot`, `#test`) of spreek met de
andere eigenaar af wie waar antwoordt.

## Commando's

De volledige lijst met alle commando's en wat ze doen staat in **[COMMANDS.md](COMMANDS.md)**. Op de mesh kun je ook
`help` typen: de bot stuurt dan de link naar die lijst, en `help <commando>` geeft uitleg over één commando.

## Met dank aan

Dit project bouwt voort op het werk van anderen:

- **[agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot)** van Adam Gessaman en anderen (MIT): de bot zelf,
  met zijn commando's, dashboard en alle instellingen (`config.ini.example`). Deze add-on gebruikt een vaste versie
  (v1.1.0) en past die bij het bouwen aan met kleine, gedocumenteerde patches (`meshcore-bot/local_patches/`). Vragen over
  de bot zelf horen daar; vragen over deze add-ons hier.
- **[MeshCore](https://github.com/meshcore-dev/MeshCore)**: de firmware en het protocol van het mesh-netwerk, en de
  Python-bibliotheken [meshcore_py](https://github.com/meshcore-dev/meshcore_py) en
  [meshcore-cli](https://github.com/meshcore-dev/meshcore-cli) waarmee de bot met de radio praat.
- **[meshcore-ha](https://github.com/meshcore-dev/meshcore-ha)** en **[MeshCore Chat](https://github.com/mwolter805/meshcore-ha-chat)**:
  de Home Assistant-integratie en het chatpaneel waar deze add-ons mee samenwerken.
- **Open data** voor de extra commando's: RDW (kentekens), NDW (files en wegwerk), OVapi (openbaar vervoer), KNMI
  (weerwaarschuwingen, aardbevingen), Rijkswaterstaat (waterstand), CBS (brandstofprijzen), EnergyZero (stroomprijs),
  Buienradar (regen), OpenStreetMap / Overpass (AED's, laadpalen), Safecast (straling), Nager.Date (feestdagen),
  Open Trivia DB (quiz) en Storingradar (storingen).

Licentie: MIT, zie [LICENSE](LICENSE). De oorspronkelijke bot valt onder zijn eigen MIT-licentie.
