# MeshCore bot commands

All commands of the **Vip|HA|🤖** MeshCore bot. The descriptions are in Dutch, like the bot's replies; the bot answers in the language you write in (Dutch, English, German or French).

**How to use:** type the command in `#bot` or `#test`, or send it as a direct message (DM) to the bot. In the public channel (channel 0) the bot does not run commands. More help on one command: `help <command>`, for example `help dx`.

Legend: **DM** = only by direct message · **#f1** = in the #f1 channel or by DM · 🌐 = needs internet

## Inhoud

- [Basis en hulp](#basis-en-hulp)
- [Mesh en radio](#mesh-en-radio)
- [Spellen en community](#spellen-en-community)
- [Formule 1](#formule-1)
- [Handig (Nederland en België)](#handig-nederland-en-belgië)
- [Weer, zon en ruimte](#weer,-zon-en-ruimte)
- [Leuk](#leuk)

## Basis en hulp

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `ping` | `ping` | Snelle controle: de bot antwoordt 'Pong!'. |
| `test`<br><sub>ook: t</sub> | `test [zin]` | Verbindingsinfo van je bericht: route, SNR, RSSI en tijd. |
| `hello`<br><sub>ook: hi, hey, hola, bonjour, ...</sub> | `hello` | Groet terug (robotstijl). Let op: 'hallo' zit er niet bij. |
| `help` | `help  /  help 2  /  help dx` | Lijst van commando's per pagina, of uitleg over één commando. |
| `helpall` | `helpall` | De volledige commandolijst, elke keer de volgende pagina. |
| `cmd`<br><sub>ook: cmds, commands</sub> | `cmd` | Korte lijst van beschikbare commando's. |
| `version`<br><sub>ook: ver</sub> | `version` | Welke versie van de bot draait. |
| `contact` | `contact` | Contactgegevens van de bot. |
| `channels`<br><sub>ook: channel</sub> | `channels [lijst\|#kanaal]` | Overzicht van bekende hashtag-kanalen. |
| `info bot`<br><sub>ook: infobot</sub> | `info bot` | Wat deze bot is en wat je nodig hebt voor een eigen bot. **DM** |

## Mesh en radio

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `pad` | `pad` | De route van je bericht in één regel: hops, km en repeaters (? = gok). |
| `sig`<br><sub>ook: signaal</sub> | `sig` | SNR, RSSI en hops van je bericht met een oordeel (goed/redelijk/zwak). Handig bij antenne-tuning. |
| `path`<br><sub>ook: decode, route</sub> | `path  /  path 4a,c2,8c` | Lange versie van de route: elke repeater op een eigen regel. |
| `trace`<br><sub>ook: tracer</sub> | `trace [pad]` | Trace langs een pad (heen en terug), met signaal per stap. |
| `multitest`<br><sub>ook: mt</sub> | `multitest` | Luistert 6 seconden en toont alle routes waarlangs je bericht binnenkwam. |
| `prefix`<br><sub>ook: lookup</sub> | `prefix 4a` | Welke repeaters een bepaalde prefix hebben, met locatie. 🌐 |
| `meshkaart`<br><sub>ook: nodes</sub> | `meshkaart` | Hoeveel nodes, repeaters en rooms de bot hoort (24 uur, 7 dagen, ooit). |
| `whois` | `whois <naam of sleutel>` | Contactkaart van een bekende node. |
| `rptr` | `rptr  /  rptr buren  /  rptr accu 7d` | Status van de repeater van de beheerder: batterij, uptime, airtime, buren. |
| `stats` | `stats [messages\|channels\|paths\|adverts]` | Statistieken van de afgelopen 24 uur. |
| `topu` | `topu  /  topu 7` | Top 5 actiefste gebruikers (24 uur of N dagen), zonder bots. |
| `topr` | `topr  /  topr 7` | Top 3 drukste repeaters. |
| `topc` | `topc  /  topc 7` | Top 5 meest gebruikte commando's. |
| `uptime` | `uptime` | Hoe lang de bot al draait. |

## Spellen en community

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `dx` | `dx  /  dx top [week\|maand\|ooit]  /  dx ik` | DX Jacht: records voor het bericht met de meeste hops, per week, maand en ooit. |
| `xp`<br><sub>ook: level</sub> | `xp  /  xp <naam>  /  xp top [week]` | Mesh RPG: XP, level en titel. Je verdient XP met berichten, commando's, inchecken, karma en DX. |
| `badge`<br><sub>ook: badges</sub> | `badge  /  badge <naam>` | Mesh RPG: je behaalde mijlpalen (berichten, actieve dagen, hops, reeksen, karma, levels). |
| `karma`<br><sub>ook: topkarma</sub> | `karma <naam>  /  karma  /  karma top` | Bedank iemand met een punt (max 3 per dag, niet jezelf of een bot). |
| `checkin`<br><sub>ook: meld, inchecken</sub> | `checkin  /  checkin top` | Dagelijks inchecken en een reeks opbouwen. |
| `voorspel` | `voorspel  /  voorspel nieuw Vraag? \| ja \| nee  /  voorspel 1` | Voorspellingsspel voor elke vraag. Vragen stellen en antwoorden via DM; 1 punt voor een goed antwoord. |
| `peiling`<br><sub>ook: kies</sub> | `peiling Waar eten we? \| pizza \| friet  →  kies 2` | Meerkeuze-peiling op een kanaal (2 tot 5 keuzes), stemmen met kies <nr>. |
| `stem`<br><sub>ook: poll, ja, nee</sub> | `stem 15m pizza vanavond?  →  ja / nee` | Ja/nee-stemming op een kanaal. |
| `prikbord` | `prikbord  /  prikbord pomp te leen  /  prikbord weg 3` | Prikbord: korte berichten die 7 dagen blijven staan. |
| `quiz` | `quiz` | Quizvraag op het kanaal. |
| `hangman` | `hangman` | Galgje op het kanaal. |
| `dice` | `dice 2d6` | Dobbelstenen gooien. |
| `roll` | `roll 100` | Willekeurig getal van 1 tot en met het getal. |
| `magic8` | `magic8 Wordt het droog?` | De Magic 8-Ball beantwoordt een ja/nee-vraag. |

## Formule 1

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `f1` | `f1  /  f1 stand  /  f1 uitslag  /  f1 nu  /  f1 voorspel VER  /  f1 spel` | Volgende race, WK-stand, uitslag, live sessie en het F1-voorspellingsspel (voorspellen via DM). **#f1** |

## Handig (Nederland en België)

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `herinner`<br><sub>ook: remind</sub> | `herinner 30m pizza  /  herinner 18:30 antenne  /  herinner lijst` | Persoonlijke herinnering, je krijgt een DM op het gekozen moment. **DM** |
| `noodnummers`<br><sub>ook: nood</sub> | `noodnummers` | 112 en de regionale hulpnummers. In een kanaal gevraagd komt het antwoord als DM. |
| `aed` | `aed Heerlen` | De dichtstbijzijnde AED's. In een kanaal gevraagd komt het antwoord als DM. 🌐 |
| `buien`<br><sub>ook: buienradar</sub> | `buien  /  buien Weert` | Regen de komende 2 uur, per 10 minuten (Buienradar). 🌐 |
| `weerwaarschuwing`<br><sub>ook: gladheid</sub> | `weerwaarschuwing` | Actuele KNMI-weerwaarschuwing. 🌐 |
| `beving` | `beving` | Recente aardbevingen in en rond Nederland (KNMI). 🌐 |
| `storing` | `storing kpn` | Storingen bij een telecomprovider. 🌐 |
| `file` | `file Maastricht` | Files en ongevallen bij een plaats. 🌐 |
| `wegwerk` | `wegwerk Sittard` | Wegwerkzaamheden bij een plaats. 🌐 |
| `ov` | `ov Heerlen station` | Eerstvolgende vertrektijden van het openbaar vervoer. 🌐 |
| `tanken` | `tanken` | Landelijke gemiddelde brandstofprijzen van vandaag (CBS). 🌐 |
| `laadpaal` | `laadpaal Kerkrade` | Laadpalen in de buurt. 🌐 |
| `energieprijs` | `energieprijs` | Huidige dynamische stroomprijs. 🌐 |
| `waterstand` | `waterstand` | Waterstand van de Maas. 🌐 |
| `straling` | `straling Maastricht` | Indicatief stralingsniveau. 🌐 |
| `kenteken` | `kenteken HDJ-60-R` | Nederlands kenteken opzoeken (RDW). Belgische en Duitse kentekens niet (geen gratis bron). 🌐 |
| `feestdag`<br><sub>ook: vandaag</sub> | `feestdag` | Feestdagen in Nederland en België. |

## Weer, zon en ruimte

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `wx`<br><sub>ook: weather</sub> | `wx Heerlen  /  wx Heerlen 7d` | Weerbericht voor een plaats. 🌐 |
| `rain`<br><sub>ook: nowcast, snow</sub> | `rain Heerlen` | Wanneer het gaat regenen of sneeuwen (ook buiten NL/BE). 🌐 |
| `aqi`<br><sub>ook: air, airquality</sub> | `aqi Maastricht` | Luchtkwaliteit voor een plaats. 🌐 |
| `sun` | `sun` | Zonsopgang en zonsondergang. |
| `moon` | `moon` | Maanfase en opkomst/ondergang. |
| `aurora`<br><sub>ook: kp</sub> | `aurora` | Noorderlicht-voorspelling (KP-index). 🌐 |
| `solar` | `solar` | Zonnecondities en HF-banden. 🌐 |
| `hfcond` | `hfcond` | HF-bandcondities voor zendamateurs. 🌐 |
| `solarforecast`<br><sub>ook: sf</sub> | `sf Heerlen 4000` | Verwachte opbrengst van zonnepanelen. 🌐 |
| `satpass` | `satpass iss` | Wanneer een satelliet overkomt. 🌐 |
| `alert`<br><sub>ook: incident</sub> | `alert <plaats>` | Actieve noodmeldingen (PulsePoint, vooral VS). 🌐 |

## Leuk

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `weetje`<br><sub>ook: wistje</sub> | `weetje` | Een willekeurig Nederlands weetje. |
| `quote`<br><sub>ook: citaat</sub> | `quote` | Een willekeurig citaat. |
| `joke`<br><sub>ook: jokes</sub> | `joke` | Een willekeurige mop (Engels). 🌐 |
| `dadjoke` | `dadjoke` | Een vadergrap (Engels). 🌐 |
| `morse` | `morse SOS` | Tekst naar morse en terug. |
| `sudo`<br><sub>ook: ls -la, rm -rf, ...</sub> | `sudo make coffee` | Doet alsof je een schurkencomputer hackt. |
| `catfact`<br><sub>ook: cat, meow</sub> | `catfact` | Kattenfeitje (verborgen commando). 🌐 |
| `sports`<br><sub>ook: score, scores</sub> | `sports ajax` | Sportuitslagen en programma. 🌐 |

## Spellen, goed om te weten

- **XP (Mesh RPG):** 1 per bericht (max 20 per dag), 2 per commando (max 10 per dag), 5 per check-in, 10 per karmapunt dat je krijgt, 5 per hop van je beste DX. Ook wat je in Publiek schrijft telt mee.
- **Bots doen niet mee** in de ranglijsten.
- `voorspel`, `herinner` en `f1 voorspel` gaan via een DM: daar zit je sleutel bij, zodat niemand namens jou kan spelen.
