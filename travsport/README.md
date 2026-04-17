# travsport

Read-only adapter swedishhorseracing.com:in JSON-backendille (Svensk
Travsport / ATG -ekosysteemi). Sisarpaketti `heppa`:lle, samalla
rakenteella: kohtelias HTTP-client, rate-limit, disk cache, adapterit.

## Vahvistetut endpointit

### Kortin tilastot (yksi kutsu per lähtö, kaikki hevoset kerralla)

```
GET /services/race/{raceId}/stats
```

Missä `raceId` on muotoa `{YYYY-MM-DD}_{trackNumber}_{raceNumber}`.
Esim. Halmstad (rata 18), lähtö 1, 17.4.2026 → `2026-04-17_18_1`.

Käytä apufunktiota:
```python
from travsport import make_race_id
race_id = make_race_id("2026-04-17", track_number=18, race_number=1)
```

Vastaus (tiivistetty):
- Dict jonka avaimet ovat `program_number` stringinä.
- Per hevonen:
  - `pastPerformances`: lista viime starteista (max ~5–10).
    - `formattedPlace`, `formattedResult` (1-15 / 0 / "k" keskeytys / "p" prov)
    - `raceDayDate` `/Date(ms)/` -muodossa (.NET epoch ms)
    - `trackCode`, `distance`, `formattedTime` ("22,4" = 1:22.4/km)
    - `odds` ("85,59" = 85.59 voittokerroin; "gdk"=godkänd/qualifier, "ejg"=ej godkänd)
    - `driverFullName`, `raceType` ("V"=kilpailu, "K"=kelpoisuus, "P"=prov)
  - `horseStats`: Life + vuosittain yhteenvetoja (earningSum SEK, starts, 1st/2nd/3rd)

### Puuttuvat endpointit (etsi DevToolsilla)

Vielä tarvitaan:
- **Startlist** — hevosten nimet, ohjastaja+valmentaja-ID:t, peliprosentit.
  Kokeile klikata jotain hevosta kortissa → seuraa Network-välilehteä.
  Todennäköinen URL: `/services/race/{raceId}/startlist` tai `/services/race/{raceId}`.
- **Horse profile** — hevosen syntymävuosi, ennätykset, sukulinja.
  Todennäköinen: `/services/horse/{id}` kun tiedät ID:n.

Kun löydät nämä, lisää ne `travsport/api.py`:ään samaan malliin kuin
`race_stats`.

## Käyttö

### CLI

```powershell
# Hae yhden lähdön stats kuin raw
python -m travsport.cli race-stats 2026-04-17_18_1 --raw

# Parsittu taulukko + race_model feature-frame preview
python -m travsport.cli race-stats 2026-04-17_18_1 --last-n 6

# Tallenna past_performances CSV:hen
python -m travsport.cli race-stats 2026-04-17_18_1 --out halmstad_r1.csv
```

### Python

```python
from travsport import TravsportApi, make_race_id
from travsport.client import from_env

api = TravsportApi(client=from_env())
race_id = make_race_id("2026-04-17", 18, 1)
stats = api.race_stats(race_id)

# Kaikki lähdön hevosten viimeiset startit DataFramena
print(stats.past_performances.head())

# Kausi- ja life-tilastot per hevonen
print(stats.horse_summary)

# race_model-yhteensopivat prior-listat
feats = stats.to_race_model_features(last_n=6,
                                        reference_date="2026-04-17")
```

## Integrointi ingestion-pipelineen (Halmstadia varten)

`ingestion/enrichment.py` voi käyttää travsport:ia rikastukseen
suomalais-ruotsalaisissa korteissa:

1. Veikkauksen kortin hevosten `program_number` → yhteys travsport:n
   vastaavaan lähtöön raceId:n kautta.
2. `stats.to_race_model_features()` täyttää prior-listat.
3. Ei tarvita heppaa ruotsalaisille hevosille.

Tämä on seuraava askel: `ingestion`-putkea laajennetaan niin että se
tunnistaa `track_code` ja valitsee oikean datalähteen.

## Konfigurointi

| Muuttuja | Oletus |
|----------|--------|
| `TRAVSPORT_BASE_URL` | `https://www.swedishhorseracing.com` |
| `TRAVSPORT_USER_AGENT` | projektin UA |
| `TRAVSPORT_CACHE_DIR` | `~/.cache/travsport` |
| `TRAVSPORT_MIN_INTERVAL` | `1.0` |

## Käyttöehdot

Sama kuin Hippoksen: henkilökohtainen analyysi OK, älä jakele
scrape-dataa kolmansille. Rate-limit 1 req/s oletuksena.
Tunnistaudu User-Agent-kentällä jossa on yhteystiedot.
