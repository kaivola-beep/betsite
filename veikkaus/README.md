# veikkaus

**Read-only** adapter to Veikkauksen Toto-info JSON-API:lle. Tämä paketti
hakee `/api/toto-info/v1/...` -endpointtien data, jota voidaan syöttää
`race_model`:lle ja `toto_optimizer`:lle. Paketti ei koskaan tee
vedonlyöntejä: kaikki `wager` / `bet` / `ticket` -endpointit on jätetty
tarkoituksella pois.

## Käyttöehdot ja pelisäännöt

Tämän paketin käyttö edellyttää, että **noudatat Veikkauksen
käyttöehtoja ja sport-games-robot -reposin ohjeistuksia**:

* Ilmoittaudu `X-ESA-API-Key: ROBOT` -headerillä (oletus).
* Käytä omaa `User-Agent`-tunnistetta jossa on yhteystiedot.
* Enintään **4 rinnakkaista** pyyntöä; sarjassa oletus on 1/sek.
* Älä hae kertoimien päivityksiä tiheämmin kuin kerran minuutissa.
* Älä kopioi sisältöä julkiseen jakeluun.

Virallinen viite: <https://github.com/veikkaus/sport-games-robot>.

## Moduulit

```
veikkaus/
├── client.py      # HTTP-asiakas (auth, rate limit, retry, disk cache)
├── toto.py        # TotoInfo: cards/pools/runners/odds
├── adapters.py    # Veikkaus JSON  ->  race_model / toto_optimizer
├── cli.py         # "python -m veikkaus.cli today | pools | export"
└── tests/         # mockattu HTTP, ei oikeita kutsuja
```

## Asennus

```powershell
pip install -r veikkaus/requirements.txt
```

## Käyttö

### 1. Katso tämän päivän ravit

```powershell
python -m veikkaus.cli today
```

Saat listan korttien id:istä (esim. `12345`) ja radoista.

### 2. Katso kortin poolit

```powershell
python -m veikkaus.cli pools --card-id 12345
```

### 3. Lataa data race_model-muotoon

```powershell
python -m veikkaus.cli export --card-id 12345 --format race_model --out .\today.csv
```

Syötä sitten race_modeliin:

```powershell
python -m race_model.app.main predict `
    --history .\hist.csv `
    --card .\today.csv `
    --bootstrap 20 `
    --out-csv .\predictions.csv
```

### 4. Lataa data toto_optimizer-muotoon (jackpot-ajoa varten)

```powershell
python -m veikkaus.cli export --card-id 12345 --format toto_optimizer `
    --out .\card.csv --shares-out .\shares.csv --product toto75
```

ja

```powershell
python -m toto_optimizer.app.main run `
    --card .\card.csv --pool-shares .\shares.csv `
    --product toto75 --jackpot 250000 --pool-eur 500000 --budget 20 `
    --strategy jackpot
```

## Python API

```python
from veikkaus import VeikkausClient
from veikkaus.client import from_env
from veikkaus.toto import TotoInfo
from veikkaus.adapters import to_race_model_starts, to_toto_optimizer_card

client = from_env()                     # tai VeikkausClient(...)
info = TotoInfo(client=client)

# Raakadata:
cards = info.cards_today()
pools = info.card_pools("12345")
runners = info.race_runners("R12345-1")
odds = info.pool_odds("P_WIN_1")

# Valmiiksi mapattuna:
df = to_race_model_starts(info, "12345")                     # pandas DF
card, shares = to_toto_optimizer_card(info, "12345", product="toto75")
```

## Konfigurointi ympäristömuuttujilla

| Muuttuja | Oletus | Selitys |
|----------|--------|---------|
| `VEIKKAUS_BASE_URL` | `https://www.veikkaus.fi` | API:n juuri |
| `VEIKKAUS_API_KEY` | `ROBOT` | `X-ESA-API-Key`-headerin arvo |
| `VEIKKAUS_USER_AGENT` | `toto-optimizer/0.1 ...` | Identifioi itsesi |
| `VEIKKAUS_CACHE_DIR` | `~/.cache/veikkaus` | JSON-vastausten levytallennus |
| `VEIKKAUS_MIN_INTERVAL` | `1.0` | Minimikuilu sekunteina pyyntöjen välillä |

## Testit

```powershell
pytest veikkaus/tests -q
```

Testit käyttävät mockattua HTTP:tä eivätkä tee oikeita verkkokutsuja.

## Tunnetut rajoitteet

* **JSON-kentät voivat muuttua.** `adapters.py` käyttää
  defensiivistä `_first_key(...)`-hakua useasta kandidaatista, mutta jos
  Veikkaus vaihtaa skeemaa isosti, mappaus täytyy päivittää. Sarakkeen
  `currentPool`, `jackpot`, `stakePct`, `startNumber` nimet on valittu
  yleisillä konventioilla.
* **Ei historiadataa.** Tämä endpoint antaa vain *nykyhetken* kortin.
  Historia- ja kuntodatan kerääminen on eri asia; katso erillinen
  `heppa`-moduuli Suomen Hippoksen tilastojen hakemiseen.
* **Julkinen Toto-info ei vaadi kirjautumista.** `client.login()` on
  mukana, mutta tarvitaan vain omalle tililleen (esim. saldon tarkistus),
  eikä tämä paketti käytä sitä lainkaan.

## Vastuullisuus

Paketti on analyysityökalu. Se ei veikkaa rahaa puolestasi eikä lupaa
voittoja. Pelaa vastuullisesti.
