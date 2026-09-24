# Installeren, stap voor stap

*[English](INSTALL.md) · terug naar de [README](README.nl.md)*

Deze handleiding brengt je van een lege Home Assistant naar een bot die antwoordt op de mesh. We gaan ervan uit dat je
radio al de MeshCore **companion (USB)** firmware heeft. Elke optie staat ook uitgelegd in het tabblad **Documentatie** van
elke add-on (Engels).

## 1. Voordat je begint

- **Home Assistant OS of Supervised.** Add-ons hebben de Supervisor nodig; een installatie als *Container* of *Core* kan
  ze niet draaien.
- **De radio zit met USB** aan de computer waarop Home Assistant draait.
- **Je eigen publieke sleutel** (64 tekens). Die vind je in je MeshCore-app, bij de instellingen van je eigen node. Daarmee
  weet de bot wie zijn beheerder is.
- **Welke kanalen gaat de bot gebruiken?** Vraag eerst in je regio welke kanalen al een bot hebben (zie
  [De mesh delen met andere bots](README.nl.md#de-mesh-delen-met-andere-bots)). Gebruikelijk is een kanaal `#bot` voor
  commando's en `#test` om te testen; laat het openbare kanaal aan de mensen.

## 2. De repository toevoegen

1. **Instellingen → Add-ons → Add-on Store**.
2. Rechtsboven **⋮ → Repositories**, plak `https://github.com/vipje/Meshcore-bot-for-HA` en klik **Toevoegen**.
3. Sluit het venster. **MeshCore Proxy** en **MeshCore Bot** staan nu in de store (herlaad de pagina als ze er niet staan).

## 3. MeshCore Proxy

Maar één programma tegelijk kan de USB-radio openen. De proxy opent hem één keer en deelt hem via TCP (poort 5010) met de
bot en, als je die gebruikt, meshcore-ha.

1. Open **MeshCore Proxy** en klik **Installeren**.
2. Tabblad **Configuratie**, **Seriële poort**: het pad van je radio. `/dev/ttyACM0` komt veel voor; een
   `/dev/serial/by-id/usb-...`-pad is beter, omdat het niet verandert als je andere USB-apparaten aansluit. Weet je het niet?
   Start de add-on gewoon: vindt hij de poort niet, dan staan in het tabblad **Logboek** de paden die er wel zijn.
3. Tabblad **Info**: zet **Starten bij opstarten** en **Watchdog** aan en klik **Starten**.
4. In het **Logboek** staat `Luistert op 0.0.0.0:5010`. De proxy is klaar.

**Gebruik je ook meshcore-ha?** Zet die op verbindingstype **TCP**, host `localhost`, poort `5010`, in plaats van de USB-poort.

## 4. MeshCore Bot

1. Open **MeshCore Bot** en klik **Installeren**. Home Assistant bouwt de add-on op je eigen machine; dat duurt een paar minuten.
2. Tabblad **Configuratie**. De verbinding staat al goed voor de proxy (`tcp`, `localhost`, `5010`). Vul het deel **Bot** in:

   | Optie | Wat vul je in |
   |---|---|
   | Botnaam | De naam op de mesh, bijvoorbeeld je woonplaats. Zet er geen emoji achter: `|🤖` komt er vanzelf achter. |
   | Kanalen om op te luisteren | Eén kanaal per regel, precies zoals op de radio, bijvoorbeeld `#bot` en `#test`. |
   | Admin-publieke sleutels | Je eigen publieke sleutel van 64 tekens (stap 1). |
   | Taal van de antwoorden | `nl` of `en`. |
   | Tijdzone | Bijvoorbeeld `Europe/Amsterdam`; leeg = de tijdzone van het systeem. |

   De rest kan blijven zoals het is. Klik **Opslaan**.
3. Tabblad **Info**: zet **Starten bij opstarten**, **Watchdog** en **Weergeven in zijbalk** aan en klik **Starten**.
4. In het **Logboek** zie je de bot verbinden met de proxy en zijn commando's laden.

**De kanalen moeten ook op de radio staan.** De bot hoort alleen kanalen die de radio kent. Voeg ze toe op het dashboard
(volgende stap), pagina **Radio**, bij de kanalen. Een hashtag-kanaal zoals `#bot` heeft alleen zijn naam nodig. Herstart na
het toevoegen de bot-add-on één keer, zodat hij het kanaal oppikt.

## 5. Eerste test

Vanaf je telefoon, in een van de kanalen van de bot:

- `ping` → de bot antwoordt `Pong!`
- `test` → de bot antwoordt hoe hij je bericht ontving (route, signaal)
- `help` → een link naar de commandolijst

Een direct bericht aan de bot werkt ook. Geen antwoord? Zie [Problemen oplossen](#9-problemen-oplossen).

## 6. Het dashboard

Klik in de Home Assistant-zijbalk op **MeshCore Bot**. De belangrijkste pagina's (het dashboard is Engelstalig):

| Pagina | Wat doe je daar |
|---|---|
| Dashboard | Status van de bot en de radio. |
| Mesh / Contacts | De nodes die de bot hoort, op een kaart en in een lijst. |
| Radio | Instellingen van de radio en de kanalen op de radio. |
| **Plugins** | Een kaart per commando en per service: aan- of uitzetten en instellen. |
| Bots | Welke namen als bot tellen (voor spellen, ranglijsten en "nooit een andere bot antwoorden"). |
| Games | Standen van alle spellen, zonder bots. |
| Radar | Welke kanalen er in je omgeving actief zijn (geteld zonder iets te ontsleutelen). |
| Schedule | Berichten die de bot op een vast tijdstip plaatst. |

Op **Plugins** werken kaarten van **commando's** meteen. Kaarten van **services** vragen een herstart van de add-on; dat
staat op de kaart.

## 7. Wat zet je aan

Een nieuwe installatie begint rustig: alles wat een eigen opstelling vraagt, staat uit. Het bekijken waard:

| Kaart | Wat het doet |
|---|---|
| **ChannelHint** | Maakt van het openbare kanaal een verwijskanaal: daar geen commando's, alleen een korte verwijzing naar je botkanalen. Vul *Channels that get a hint* in (bijvoorbeeld `Public`) en *Channels where commands do work* (`#bot`, `#test`). |
| **greeter** | Begroet nieuwe mensen in een kanaal. Luistert eerst 7 dagen, zodat een druk kanaal niet in één keer begroet wordt. |
| **RoomServer Login** | Logt de bot in op je room server, zodat commando's daar ook werken en meldingen erheen kunnen. |
| **Notifications** | Berichten over de bot zelf (gestart, radio weg, ...) naar een room, kanaal of DM. |
| **Webhook** | Laat Home Assistant berichten op de mesh zetten. **Zet eerst een geheime token.** |
| Community, Reminders, ChannelRadar | Spellen, `herinner` en de radar. Staan standaard aan. |

Met **meshcore-ha**: **HARepeater** (status van je repeater, `rptr`) en **HomeAssistantBridge** (de antwoorden van de bot
in het MeshCore Chat-paneel). Met de HACS-integratie *f1_sensor*: **F1** (het F1-kanaal en voorspellingsspel). Het tabblad
**Documentatie** van de add-on legt elk ervan uit.

## 8. Veiligheid

- Het dashboard is alleen bereikbaar via de Home Assistant-zijbalk (*Reachable from the network* staat uit). Laat dat zo;
  zet je poort 8081 toch open, geef dan bij **Webviewer** een wachtwoord.
- Zet de **Webhook** alleen aan met een geheime token.
- Zet bij *Admin-publieke sleutels* alleen sleutels die je vertrouwt. Admin-commando's werken alleen in echte directe berichten.

## 9. Problemen oplossen

| Probleem | Probeer |
|---|---|
| De proxy vindt de radio niet | Kijk naar de lijst met paden in het logboek van de proxy; gebruikt een andere add-on of integratie de USB-poort nog? |
| De bot maakt geen verbinding | Draait de proxy? Start eerst de proxy, dan de bot. |
| Geen antwoord in een kanaal | Staat het kanaal bij *Kanalen om op te luisteren* **én** op de radio? Herstart de bot na het toevoegen van een kanaal. |
| Helemaal geen antwoord | Zet *Bot → Logniveau* op `DEBUG`, stuur opnieuw `ping` en lees het logboek. |
| Geen antwoord in de room | De klok van de room staat misschien verkeerd; zie *Room server* in het tabblad Documentatie. |

## 10. Verhuizen naar een andere installatie

Je instellingen, spellen en database kunnen mee naar een nieuwe Home Assistant: zet een leeg bestand `EXPORT` in
`/share/meshcore-bot/`, herstart de bot, en kopieer de bestanden uit `/share/meshcore-bot/export/...` naar
`/share/meshcore-bot/import/` op de nieuwe installatie, vóór de eerste start daar. De stappen staan in het tabblad
Documentatie, *Moving the bot*.

Meer in het tabblad **Documentatie** van de bot. Vragen over deze add-ons:
[issues van deze repository](https://github.com/vipje/Meshcore-bot-for-HA/issues).
