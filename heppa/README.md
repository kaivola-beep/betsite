# heppa

Polite, read-only scraper for [heppa.hippos.fi](https://heppa.hippos.fi).
Kerää *julkisia* top-tilastoja (hevoset, ohjastajat, valmentajat) ja
palauttaa ne puhtaina pandas DataFrameina, joita voi syöttää esim.
`race_model`:in feature engineering -kerrokseen.

## Käyttöehdot — lue tämä

Heppa-tietokanta on Suomen Hippos ry:n omaisuutta. Tämä paketti on
tarkoitettu vain **henkilökohtaiseen analyysiin**:

* Älä julkaise tai jaa scraped dataa kolmansille osapuolille.
* Pidä requestit harvakseltaan. Oletuksena 1 req/sek.
* Tunnistaudu `User-Agent`-headerilla (oletus sisältää projektin
  GitHub-linkin; aseta omasi jos käytät tätä tuotannossa).
* Kunnioita `robots.txt`:ää. Tämä paketti ei automaattisesti hae
  disallow-polkuja.
* Jos Hippos ottaa käyttöön virallisen API:n, vaihda sen käyttöön.

## Moduulit

```
heppa/
├── client.py       # HTTP-asiakas (rate limit, User-Agent, levycache)
├── statistics.py   # top_horses / top_drivers / top_trainers + HTML-parser
├── cli.py          # python -m heppa.cli horses ...
├── fixtures/       # HTML-näytteet testeille
├── tests/          # mockatut HTTP-testit
├── requirements.txt
└── README.md
```

## Asennus

```powershell
pip install -r heppa/requirements.txt
```

`lxml` on pakollinen `pandas.read_html`:ää varten.

## Käytetyt endpoint-polut

Hippos käyttää **kahta eri URL-muotoa**, ei yhtä yhtenäistä rajapintaa.

### Hevoset (vahvistettu)

```
GET /heppa2_backend/statistics/best/horses
    ?species=L&startDate=2023-01-01&endDate=2023-12-31
    &limit=10&onlyRegisteredInFinland=true
```

Query-parametrit: `species` (`L` lämminveri / `S` suomenhevonen /
`P` poni), `startDate`, `endDate`, `limit`, `onlyRegisteredInFinland`.

Vastauksen rakenne per hevonen: `horseId`, `name`, `species`, `gender`
(R/O/T), `birthYear`, `birthCountry`, `registrationCountry`, `starts`,
`prizeSum`, `firstPlaces`, `secondPlaces`, `thirdPlaces`, `monte`,
`photo`.

### Ohjastajat (vahvistettu)

```
GET /heppa2_backend/statistics/risingshape/driver/2026-01-01/2026-12-31
    ?track=ALL&limit=30&order=WINS&horseStarts=true&ponyStarts=false
```

Täysin eri muotoa kuin horses: **päivämäärät ovat polkusegmenttejä**,
ja query-parametrit koskevat lähtötyyppiä (horse/pony) eivätkä rotua.

Vastauksen rakenne per ohjastaja: `start`, `wins`, `secondPlaces`,
`thirdPlaces`, `priceMoneys`, `winPercentage`, `priceMoneyForStart`,
`winOddsSumForStart`, `personName`, `firstName`, `lastName`,
`personId`, `photo`.

Paketti normalisoi nämä sarakkeisiin joissa on sekä raakaluvut että
kaksi erityisen hyödyllistä kenttää featureiksi:
- `earnings_per_start` — ohjastajan skaalattu laatuindeksi (€/startti).
- `win_odds_per_start` — voittokerrointen summa / startti eli
  indikaatio kuinka paljon ohjastajan voittajat maksavat (korkeampi =
  ohjastaja voittaa enemmän pitkävetoja).

### Valmentajat (arvaus, sama sapluuna)

```
GET /heppa2_backend/statistics/risingshape/trainer/{start}/{end}
```

Oletuksena kokeillaan `trainer`-polkua. Jos 404, etsi oikea polku
DevTools-metodilla (ks. Troubleshooting-osio) ja ohita oletuspolku
joko `--path`-lipulla tai ympäristömuuttujalla
`HIPPO_TRAINER_TEMPLATE`.

## Käyttö

### CLI

```powershell
# Top lämminveriset 2023 (species-parametri vain hevosilla)
python -m heppa.cli horses --discipline warmblood --start 2023-01-01 --end 2023-12-31 --out .\top_horses_2023.csv

# Top ohjastajat 2026 (ei discipline-parametria; käytä --horse-starts / --pony-starts)
python -m heppa.cli drivers --start 2026-01-01 --end 2026-12-31 --limit 30 --order WINS --out .\top_drivers.csv

# Top valmentajat (sama signature kuin drivers)
python -m heppa.cli trainers --start 2026-01-01 --end 2026-12-31 --limit 30 --out .\top_trainers.csv

# Tarkista yhden rivin JSON (debug)
python -m heppa.cli drivers --start 2026-01-01 --end 2026-12-31 --raw
```

### Python

```python
from heppa import HeppaStatistics
from heppa.client import from_env

stats = HeppaStatistics(client=from_env())
horses = stats.top_horses(discipline="warmblood",
                           start_date="2023-01-01", end_date="2023-12-31")
print(horses.head())
#    rank            name  starts  wins  seconds  thirds  win_pct  earnings
# 0     1        Tähtivalo      18     7        4       2     38.9   45200.0
# ...
```

Sarakenimet normalisoidaan automaattisesti (`Sija -> rank`, `Nimi ->
name`, `Startit -> starts`, `V -> wins`, jne.). Jos sivurakenne
muuttuu ja parseri löytää tunnistamattomia sarakkeita, ne näkyvät
`df.attrs["unmapped"]`-listassa — silloin päivitä `HEADER_MAP` tiedostossa
`heppa/statistics.py`.

## Integrointi race_modeliin

Yhdistä top-hevosten palkkiot hevosen kuntofeatureksi:

```python
import pandas as pd
from race_model.data.loaders import load_starts_from_csv
from heppa import HeppaStatistics
from heppa.client import from_env

starts = load_starts_from_csv("hist.csv")            # race_model schema
top = HeppaStatistics(client=from_env()).top_horses(
    start_date="2023-01-01", end_date="2023-12-31")
top["name_norm"] = top["name"].str.lower().str.strip()
starts["name_norm"] = starts["horse_id"].str.lower().str.strip()  # tai horse name jos saatavilla

merged = starts.merge(
    top[["name_norm", "win_pct", "earnings"]],
    on="name_norm", how="left",
    suffixes=("", "_season"),
)
```

Samaa logiikkaa voit soveltaa `top_drivers`- ja `top_trainers`-dataan:
liitetään `driver_id` / `trainer_id` -sarakkeisiin.

## Konfigurointi ympäristömuuttujilla

| Muuttuja | Oletus | Selitys |
|----------|--------|---------|
| `HEPPA_BASE_URL` | `https://heppa.hippos.fi` | Juuri |
| `HEPPA_USER_AGENT` | *Projektin UA* | Tunniste |
| `HEPPA_CACHE_DIR` | `~/.cache/heppa` | HTML-vastausten cache |
| `HEPPA_MIN_INTERVAL` | `1.0` | Min. väli sekunneissa |

## Testit

```powershell
pytest heppa/tests -q
```

Testit käyttävät mukana toimitettuja `fixtures/*.html`-tiedostoja eivätkä
tee oikeita verkkokutsuja.

## Troubleshooting — "No tables found" / SPA

Jos saat virheen:
```
HeppaError: No HTML tables found in the response.
```
se tarkoittaa lähes aina, että heppa.hippos.fi on **JavaScript-SPA** ja
palauttaa aluksi tyhjän HTML-rungon — todellinen data haetaan
selaimessa XHR-pyynnöllä JSON:ina. `requests.get()` ei osaa ajaa
JavaScriptiä, joten näet vain sen tyhjän rungon.

### Vaihe 1: Paikanna oikea JSON-endpoint

Aja:
```powershell
python -m heppa.cli inspect `
    --path "/mobiili/statistics/horses/top/warmblood" `
    --start 2023-01-01 --end 2023-12-31
```
Komento tulostaa listan URL:ista, jotka sivu referoi — useimmiten
oikea endpoint on muotoa
`/heppa-api/...`, `/rest/...`, tai jotakin vastaavaa.

Jos diagnostiikka ei löydä kandidaatteja, avaa itse selaimen Dev Tools:
1. Avaa [heppa.hippos.fi/mobiili/statistics/horses/top/warmblood](https://heppa.hippos.fi/mobiili/statistics/horses/top/warmblood).
2. Paina `F12` → välilehti **Network** → suodatin **XHR / Fetch**.
3. Lataa sivu uudelleen (`F5`).
4. Etsi pyyntö, jonka response on JSON ja sisältää hevoslistan.
5. Kopioi sen URL.

### Vaihe 2: Kutsu sitä suoraan

```python
from heppa.client import from_env
from heppa.discover import fetch_json

client = from_env()
data = fetch_json(client,
                  "/heppa-api/statistics/horses/top",   # ← oikea URL
                  params={"discipline": "warmblood",
                          "startDate": "2023-01-01",
                          "endDate": "2023-12-31",
                          "monte": "x"})
print(data[:3])
```
Kun tiedät oikean URL:n ja JSON-rakenteen, päivitä
`heppa/statistics.py` hakemaan JSON:ia HTML:n sijaan. Siinä vaiheessa
parseri muuttuu täysin triviaaliksi.

### Vaihtoehto: headless-selain

Jos datan hakeminen vaatii JavaScriptin ajamisen (harvinaista, useimmat
SPA:t hakevat datan yksinkertaisella fetchillä jonka voi toistaa),
käytä Playwrightiä:
```powershell
pip install playwright
playwright install chromium
```
Älä käytä tätä polkua oletuksena — se on paljon hitaampaa ja rasittaa
Hippoksen palveluita enemmän.

## Tunnetut rajoitteet

* **HTML-pohjainen.** Jos Hippos uudelleenjärjestää sivun, parseri hajoaa.
  Päivitä tällöin `HEADER_MAP` ja/tai heuristiikka.
* **Vain top-listat.** Hevoskohtainen historia startilta-startille vaatii
  muita sivuja; tämä paketti on tarkoituksella minimalistinen. Lisää
  samaa sapluunaa noudattavat parserit tarvittaessa.
* **Ei virallinen adapteri.** Jos Hippos julkaisee virallisen API:n,
  vaihda sen käyttöön ja arkistoi tämä moduuli.
