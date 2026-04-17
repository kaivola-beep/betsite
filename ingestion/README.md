# ingestion

Liimakerros joka yhdistää `veikkaus`, `heppa` ja oman yksinkertaisen
skooraajan yhteen CLI:hin. Syötteenä Veikkaus-kortti-ID, tulosteena
hevoskohtaiset voittotodennäköisyydet, fair odds, epävarmuus ja edge
markkinaan.

## V1-skooraaja (ilman historiadatakoulutusta)

Malli on tarkoituksellisesti läpinäkyvä log-lineaarinen sekoitus:

```
form_z   = -z(mean(viimeiset sijoitukset))        # pieni sijoitus = parempi
speed_z  = -z(mean(km-ajat sekunneissa))          # pieni = parempi
class_z  =  z(log1p(earnings_per_start))
quality_z=  z(log1p(sum(palkkiot)))
gallop_z = -z(gallop_risk)
layoff_z = -z(days_since_last_start)
market_z =  z(logit(market_share))

score = w · features  ->  softmax per lähtö
```

Oletuspainot (`ScoringWeights`): form 0.22, speed 0.18, class 0.12,
quality 0.10, gallop 0.08, layoff 0.05, **market 0.35**. Markkinan
paino on tahallaan iso — olemme rehellisiä että yksittäisen
historiapyynnön varassa ei pysty voittamaan pooliin sisältyvää
informaatiota. Kun historiadata kertyy, `race_model`in koulutettu
malli tulee tilalle ja painojen voi antaa siirtyä.

Bootstrap-epävarmuus (`score_bootstrap`) häiritsee painoja Dirichlet-
kohinalla ja laskee keskihajonnan ja 5–95 %:n kvantiilit per hevonen.

## Komennot

```powershell
# Kortit tänään (käytetään valitsemaan oikea cardId)
python -m ingestion.pipeline today

# Diagnoosi: mitä dataa kortille on saatavilla?
python -m ingestion.pipeline inspect-card --card-id 443210972

# Koko putki (hae kortti, rikasta heppa-historialla, skoori, tulosta)
python -m ingestion.pipeline predict --card-id 443210972 --last-n 20 --bootstrap 20 --out predictions.csv
```

Lisävaihtoehdot:

* `--horse-map .\manual_map.csv` — manuaalinen `horse_name,hippo_horse_id` -mappaus.
* `--name-search` — yrittää automaattisesti hakea heppa:sta nimihaulla (endpoint ei
  vielä vahvistettu; 0 % takuu).
* `--ref-date 2026-04-25` — laskee `days_since_last_start` eri referenssipäivästä.
* `--no-per-race` — piilota lähtökohtainen taulukko, näytä vain top-edge.
* `--max-workers 4` — rinnakkaisten heppa-pyyntöjen määrä (max 4 kunnioittaaksemme
  veikkaus/sport-games-robot -ohjeistusta).

## Hevos-ID-mappaus (se kriittinen pullonkaula)

Veikkaus palauttaa kortin hevosille oman `horseId`-tunnisteen.
Heppa-tietokannassa on oma `horseId`. Näiden yhdistämiseen kolme
strategiaa, käytetty tässä järjestyksessä:

1. **Inline-kenttä.** Jos Veikkauksen JSON sisältää
   `hippoHorseId` / `horseRegistryId` / `registryId`, pipeline ottaa sen suoraan.
   Kokeile: `python -m veikkaus.cli export --card-id X --format race_model --out card.csv`
   ja katso tuleeko `hippo_horse_id` täyteen.
2. **Manuaalinen mappaus.** Jos inline puuttuu, tee CSV:
   ```
   horse_name,hippo_horse_id
   Hierro Boko,2180824875766618301
   Crepe Match,2599760118389242366
   ```
   ja syötä `--horse-map map.csv`.
3. **Nimihaku.** Opt-in `--name-search`. Kokeillaan pariin arvauspolkuun
   (`/heppa2_backend/horse/search` jne.); käytännössä endpoint pitää vielä
   löytää DevToolsista. Kun se tunnetaan, hakua voi laajentaa
   `heppa/discover.py`:ssa.

## Esimerkki: Halmstad Toto64 jackpot-kortti

```powershell
# 1) Selvitä cardId
python -m ingestion.pipeline today

# 2) Diagnosoi
python -m ingestion.pipeline inspect-card --card-id <Halmstadin cardId>

# 3) Tee mappaus jos tarpeen (manuaalisesti Heppan profiilista)
#    Esim. card_halmstad.csv:
#    horse_name,hippo_horse_id
#    ...

# 4) Aja koko putki
python -m ingestion.pipeline predict `
    --card-id <Halmstadin cardId> `
    --last-n 20 --bootstrap 20 `
    --horse-map .\card_halmstad.csv `
    --out halmstad_predictions.csv
```

CSV sisältää kaiken: `race_id`, `program_number`, `horse_name`,
`driver_name`, `p_model`, `p_model_sd`, `p_model_p05`, `p_model_p95`,
`market_share`, `p_market_implied`, `edge`, `fair_odds`,
`fair_odds_conservative`, per-hevosen priors.

## Rajoitteet

* **Ei vielä todellista koulutettua mallia.** V1-skoori on heuristinen
  (painotettu z-sekoitus); arvot ovat hyvä *priori* mutta eivät korvaa
  koulutettua mallia. Kun kerätään 100+ ajettua lähtöä heppa:sta,
  `race_model` voidaan kouluttaa ja asentaa V2-skoorimoottoriksi.
* **Hevos-ID-mappaus osittain manuaalinen.** Katso yllä.
* **Ei vielä lähtökohtaisia opponent-historioita.** Opponent-strength
  lasketaan nyt `log(winOdds)`-proxyllä hevosen omista starteista,
  ei vastustajien historiasta. Oikea lähtökohtainen vertailu vaatii
  kaikkien lähtöihin osallistuneiden hevosten historiat — iso urakka
  mutta lisättävissä.
