# The Market Ledger

Passordbeskyttet, virtuelt handelsblad for ASK- og IKZ-papirhandel. Siden er stylet som et avisoppslag i samme familie som *The Portfolio Times* (kremen papir, fraktur-tittel, doble strekrammer). Innholdet er på bokmål.

Live: https://hatlem72-creator.github.io/ledger-trading/

Dette er **simulert handel**. Ingen ekte penger og ingen ekte meglerordre.

## Hva som vises

- Samlet oversikt for begge kontoer (kontanter, markedsverdi, totalverdi og avkastning mot 100 000 kr)
- ASK og IKZ hver for seg med samme tall
- Beholdningstabeller (ticker, navn, antall, kjøpskurs, kurs nå, verdi, urealisert G/T)
- **Kjøpt og solgt** — full handelslogg, kan filtreres på konto, med realisert G/T på salg
- Verdi over tid (starter med åpningspunktet, fylles ut etter daglige sluttkurser)
- Tidspunkt for siste oppdatering i tidssonen Europe/Oslo
- Tydelig merket som virtuelt

## Kontoer og regler

| Konto | Formål | Start |
| --- | --- | --- |
| ASK (Aksjesparekonto) | Norske og EØS-aksjer og fond, typisk Oslo Børs | 50 000 kr |
| IKZ | Utenlandske aksjer og ETF-er (ETF-er er tillatt fordi kontoen er virtuell) | 50 000 kr |

- Mål: tjene mest mulig.
- Kurtasje: **fast 75 kr per kjøp og per salg**. Dette er en forenkling etter «75 kr eller samme som Nordnet», ikke Nordnets faktiske prisliste (som varierer med marked og beløp).
- Bare hele aksjer. Ingen brøk.
- «Cash is trash»: nesten all kasse skal være investert. Kontantresten skal bare være det hele aksjer og kurtasjen tvinger fram (sikte mot under ca. 1–2 % kasse per konto).
- Gjennomsnittskurs i NOK **uten** kurtasje. Kurtasjen trekkes fra kontanter og inngår i totalavkastningen.
- Realisert gevinst/tap ved salg = salgsprovenu minus kurtasje minus gjennomsnittskostnad for de solgte aksjene.
- Utenlandske kurser omregnes til NOK med offisiell valutakurs som lagres i tilstanden (kurs og kilde).

## Passord og kryptering

Siden på GitHub Pages er et låst skall. Selve bladet er kryptert med AES-GCM. Nøkkelen utledes i nettleseren med PBKDF2-SHA-256 (250 000 runder). Uten passord er verken HTML eller porteføljedata lesbare i det offentlige repositoriet.

Passordet ligger **bare** i `pw.txt` lokalt (rettigheter 600) og er oppført i `.gitignore`. Den filen skal aldri committes, vises i README eller limes inn i chat.

Tilstanden (`state.json`) er også gitignorert, fordi den inneholder hele porteføljen i klartekst.

## Daglig oppdatering (etter børsene er stengt)

Kjør dette på hverdager **etter at USA-børsen er stengt**, altså etter cirka 22:15 Europe/Oslo (Oslo Børs stenger 16:25, USA typisk 22:00 norsk vintertid). Da hentes sluttkurser, et nytt punkt legges inn i verdikurven, siden bygges og lastes opp.

```bash
cd /workspace/ledger-trading
./build.sh --update --push
```

Bare bygg uten å hente nye kurser, for eksempel etter en manuell handel i `state.json`:

```bash
./build.sh --push
```

Bare bygg lokalt, uten å laste opp:

```bash
./build.sh
```

### Hva skriptet gjør

1. Leser `state.json` fra den vedvarende stien  
   `/cursor/stores/store-a2949f1e-d5b4-40ef-9663-3d29b9ebfd5b/papertrading/state.json`  
   hvis den finnes, ellers fra lokal `state.json`. Du kan overstyre med `STATE_PATH`.
2. Med `--update`: `update_prices.py` henter valutakurser og papirkurser, regner om verdier og legger til historikk. Ingen handler utføres automatisk.
3. `render.py` lager avis-HTML fra tilstanden.
4. `encrypt.py` krypterer HTML-en med passordet i `pw.txt` og skriver `index.html`.
5. En runde dekryptering sjekker at låsen virker, uten å skrive ut passordet.
6. Med `--push`: `index.html` (og ev. skript) committes og lastes opp til GitHub Pages. `pw.txt` og `state.json` avvises hvis de skulle være staged.

Git-autor ved commit: `hatlem72-creator` / `hatlem72-creator@users.noreply.github.com`.

### Kurser og valuta

- **Valuta:** Norges Banks offisielle midtkurser  
  `https://data.norges-bank.no/api/data/EXR/B.USD+EUR+DKK.NOK.SP?lastNObservations=1&format=sdmx-json`  
  DKK oppgis per 100 og omregnes til kurs per 1 DKK. Hentetidspunkt og virkningsdato lagres i `state.json`.
- **Aksjer og ETF-er:** Yahoo Finance chart-API  
  `https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}?interval=1d&range=5d`  
  Hvis et papir ikke kan hentes, beholdes forrige kurs og det noteres i tilstanden. Finn ikke på kurser.
- Åpningshandelene 11. november 2026 brukte forsinkede Oslo-kurser fra stockanalysis.com samme formiddag, og offisielle USA-sluttkurser 10. november 2026 kl. 22:00 Europe/Oslo, pluss Norges Banks USD/NOK 9,4663 fra 10. november.

### Manual handel (valgfritt, før bygg)

Skriptet handler ikke av seg selv. En manuell kjøp/salg gjøres i `state.json` (hele aksjer, trekk 75 kr i kurtasje, oppdater kasse, beholdning, snittkurs og handelslogg), deretter `./build.sh --push`. Hold «cash is trash»-regelen.

## Filer

| Fil | Rolle |
| --- | --- |
| `build.sh` | Bygg og ev. last opp |
| `render.py` | HTML fra `state.json` |
| `encrypt.py` | AES-GCM + PBKDF2-låsen |
| `update_prices.py` | Hent sluttkurser og historikk |
| `verify_decrypt.py` | Sjekk at passordet låser opp, uten å vise det |
| `index.html` | Publisert, kryptert skall |
| `fonts/UnifrakturMaguntia.woff` | Fraktur-skrift til tittelen (SIL OFL) |
| `pw.txt` | Bare lokalt, aldri i git |
| `state.json` | Bare lokalt / i intern store, aldri i git |

## Krav

Python 3 med pakken `cryptography`, og `git` + `gh` for opplasting.
