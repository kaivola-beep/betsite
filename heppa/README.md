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

## Käyttö

### CLI

```powershell
# Top lämminveriset 2023
python -m heppa.cli horses --discipline warmblood --start 2023-01-01 --end 2023-12-31 --out .\top_horses_2023.csv

# Top ohjastajat kylmäveri
python -m heppa.cli drivers --discipline coldblood --start 2024-01-01 --end 2024-12-31 --out .\top_drivers_2024.csv

# Top valmentajat
python -m heppa.cli trainers --discipline warmblood --out .\top_trainers.csv
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

## Tunnetut rajoitteet

* **HTML-pohjainen.** Jos Hippos uudelleenjärjestää sivun, parseri hajoaa.
  Päivitä tällöin `HEADER_MAP` ja/tai heuristiikka.
* **Vain top-listat.** Hevoskohtainen historia startilta-startille vaatii
  muita sivuja; tämä paketti on tarkoituksella minimalistinen. Lisää
  samaa sapluunaa noudattavat parserit tarvittaessa.
* **Ei virallinen adapteri.** Jos Hippos julkaisee virallisen API:n,
  vaihda sen käyttöön ja arkistoi tämä moduuli.
