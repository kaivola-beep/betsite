# race_model

Race-aware probabilistic modelling for horse racing. Focused on
producing **well-calibrated per-horse win probabilities** rather than
point predictions of the winner.

## Mitä se tekee

1. Lukee historiadatan (CSV tai synteettinen).
2. Rakentaa race-aware feature setin (z-skaalattu lähdön sisällä,
   opponent-adjusted, missingness-flagit, interaktiot).
3. Kouluttaa ennustepinon:
   * Plackett-Luce -baseline (multinomial logit).
   * Gradient-boosted head (LightGBM LambdaRank jos saatavilla, muuten
     sklearn `HistGradientBoostingClassifier` + per-race softmax).
   * Log-lineaarinen ensemble (+ valinnainen markkinakanava).
   * Kalibrointikerros: temperature scaling ja/tai isotonic +
     race-renormalisointi.
4. Raportoi kalibroinnin laatua:
   * log-loss, Brier, ECE, reliability curve.
   * Bucket-raportit race-size / prob-bucket / aikaikkuna / start_type
     -tasoilla.
5. Antaa per-hevosen **epävarmuuden**: race-level block bootstrap →
   mean / sd / 5–95 % quantiileja.
6. Laskee fair odds ja markkinavertailun (edge, implied probability).
7. Validointi aikajärjestyksessä: rolling-origin walk-forward ja
   fold-kohtaiset metriikat → out-of-time -stabiilius näkyy suoraan.

## Vaiheittainen toteutussuunnitelma

| Vaihe | Moduuli | Miksi |
|-------|---------|-------|
| 1 | `data/schemas.py`, `data/loaders.py` | Ilman skeemaa ja luotettavaa latausta pipeline on sokea |
| 2 | `features/engineering.py` | Race-aware muuttujat + missingness → kaikki mallit pohjautuvat näihin |
| 3 | `models/baseline.py` | Plackett-Luce on tulkittava baseline, joka summautuu tasan 1 |
| 4 | `models/boosted.py` | Vahvempi päämalli; sklearn-fallback varmistaa että V1 toimii |
| 5 | `models/ensemble.py` + `models/stack.py` | Log-lineaarinen blend + pipeline-orkestrointi |
| 6 | `calibration/` | Temperature scaling ja isotonic, + kaikki metriikat |
| 7 | `models/uncertainty.py` | Race-level block bootstrap → piste-estimaatista jakaumaksi |
| 8 | `evaluation/` | Walk-forward + bucketed diagnostics = aidot OOF-luvut |
| 9 | `market/compare.py` | Erilliset fair odds ja edge, ei sekoitettu ennusteeseen |
| 10 | `app/main.py`, `app/ui.py` | Typer CLI + Streamlit UI |
| 11 | `tests/` | pytest-testit kaikille keskeisille komponenteille |

## Projektirakenne

```
race_model/
├── app/{main.py, ui.py}
├── calibration/{methods.py, metrics.py}
├── config/settings.py
├── data/{schemas.py, loaders.py, sample/sample_history.csv}
├── evaluation/{backtest.py, diagnostics.py}
├── features/engineering.py
├── market/compare.py
├── models/{baseline.py, boosted.py, ensemble.py, stack.py, uncertainty.py}
├── simulation/race_sim.py
├── tests/{test_features.py, test_baseline.py, test_boosted.py,
│         test_calibration.py, test_backtest.py, test_uncertainty.py,
│         test_market.py}
├── requirements.txt
└── README.md
```

## Asennus

```bash
cd race_model
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.10+. `lightgbm` on valinnainen; ilman sitä käytetään
`HistGradientBoostingClassifier`ia fallbackina.

## Mallin treenaaminen

```bash
# 1) Generoi synteettinen historia (V1-demo)
python -m race_model.app.main gen-history --out /tmp/hist.csv --n-races 300

# 2) Walk-forward-backtest, bucketed calibration
python -m race_model.app.main evaluate --history /tmp/hist.csv --k-folds 5

# 3) Markkinadatan kanssa
python -m race_model.app.main evaluate --history /tmp/hist.csv --use-market
```

## Ennusteiden ajaminen

```bash
python -m race_model.app.main predict \
    --history race_model/data/sample/sample_history.csv \
    --card /tmp/card.csv \
    --bootstrap 20 \
    --out-csv /tmp/predictions.csv
```

Ohjelma:
1. Rakentaa featuret historialle ja kortille.
2. Kouluttaa stackin (baseline + boosted + ensemble + kalibraatio).
3. Ajaa baseline-mallin bootstrap-wrapperin (race-level blocks).
4. Liittää fair odds -kertoimet ja edge-taulun (jos `market_share`
   löytyy kortista).

## Streamlit-käyttöliittymä

```bash
streamlit run race_model/app/ui.py
```

UI:ssä voit
* ladata historian (CSV) tai generoida synteettisen,
* valita `with_market` / `no_market`,
* valita kalibrointitavan,
* valita lähdön ja nähdä per-hevosen tn / fair odds / epävarmuus / edge,
* ajaa walk-forward-backtestin ja tarkastella reliability curvea +
  bucket-raportteja.

## Kalibroinnin arviointi

Tärkein mittari on **out-of-fold log-loss** walk-forwardista. Lisäksi:
* **Brier score**, **ECE**: ryhmittäin (race size, prob bucket, aika,
  start-type). Etsi bucketteja, joissa ECE > 0.03 — siellä malli on
  miskalibroitu.
* **Reliability curve**: jos pisteet menevät diagonaalin yläpuolelle,
  malli on alikvalitettava (underconfident) kyseisessä osassa; alapuolelle
  → overconfident.
* **Stabiilius**: `WalkForwardResult.stability()` palauttaa fold-kohtaisten
  metriikoiden keskiarvon ja keskihajonnan. Jos `log_loss_sd`/`log_loss_mean`
  on suuri, malli vaatii regularisointia tai lisää dataa.

## Matematiikka tiivistettynä

**Plackett-Luce baseline.** Vahvuus `λ_i = exp(β·x_i)`,
`P(i voittaa) = λ_i / Σ_j λ_j`. Sovitetaan MLE+L2-ridgellä L-BFGS-B:llä.

**Boosted head.** Point-wise ``is_winner`` -luokittelija tuottaa
raakaskoret, jotka muunnetaan lähtökohtaiseksi PMF:ksi per-race
softmaxilla: `p_i = exp(z_i)/Σ exp(z_j)`.

**Log-lineaarinen ensemble.** `p_ens,i ∝ Π_k p_k,i^w_k`, normalisoituna
per lähtö. Tämä on external-Bayesian opinion pool (Genest & Zidek, 1986)
ja säilyttää kalibroinnin paremmin kuin lineaarinen keskiarvo kun
komponentit ovat kalibroituja.

**Temperature scaling.** Minimoi `−(1/R) Σ_r log softmax(z_r/T)[winner_r]`
skalaarin `T` yli. Räätöli säilyy lähtökohtaisena.

**Isotonic + renormalisointi.** Isotoninen regressio hakee monotonisen
`f̂: [0,1] → [0,1]` kuvauksen marginaalille; per-race normalisointi
palauttaa PMF-ominaisuuden.

**Bootstrap-epävarmuus.** B kertaa resampling lähdöistä korvauksella,
malli koulutetaan uudelleen, aggregoidaan `p_mean`, `sd`, `p05`, `p95`.

**Fair odds ja edge.** `fair_odds = 1/p`;
`edge = p_model/p_market`; `log_edge = log(p/q)`. Ennuste ja
markkinavertailu pidetään aina erillään; markkinadata voi olla
kolmantena kanavana ensemblessä (`build_stack_with_market`), mutta
edge lasketaan aina alkuperäisiä markkinaosuuksia vasten.

## Esimerkki yhdestä lähdöstä

Tällä generaattoriseedillä malli ajettu valmiiksi; näin yhden lähdön
loppuraportti näyttää (synteettinen data, 60 lähtöä treeniä):

```
Race R0060
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ program_number ┃ p_baseline┃ p_boosted ┃ p_ens      ┃ fair_odds  ┃ p_sd   ┃ p_p95  ┃ p_market_implied┃ edge  ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 3              │ 22.1 %    │ 24.6 %    │ 23.8 %     │ 4.20       │ 3.1 %  │ 29.5 % │ 18.0 %          │ 1.32  │
│ 1              │ 17.8 %    │ 15.9 %    │ 16.6 %     │ 6.02       │ 2.8 %  │ 21.3 % │ 22.5 %          │ 0.74  │
│ …              │           │           │            │            │        │        │                 │       │
└────────────────┴───────────┴───────────┴────────────┴────────────┴────────┴────────┴─────────────────┴───────┘
```

Luvut sarakkeittain:
* `p_baseline`, `p_boosted`, `p_ens`: per-lähtö-normalisoidut voittotodennäköisyydet.
* `fair_odds`: `1 / p_ens`.
* `p_sd`, `p_p95`: bootstrap-epävarmuus keskihajonnasta ja 95-% kvantiilista.
* `p_market_implied`, `edge`: Veikkauksen (tai muun markkinan) osuus ja
  `p_ens / p_market_implied`. `edge > 1` tarkoittaa alipelattua.

## Koodin laatu

```bash
pytest race_model/tests -q
```

## Rajoitteet ja V2-roadmap

* **V1 käyttää pointwise-classifieria boosted-headissa**, ei aitoa
  LambdaRank-lossia (paitsi kun `lightgbm` asennettu). Tämä on tietoinen
  valinta: V1 pyörii pelkällä sklearnilla.
* **Prior-dataa ei tarvita**, mutta kalibrointi paranee selvästi kun
  historiaa on useita satoja lähtöjä per train-fold.
* **Markkinadatan käyttö on valinnainen** ja kapseloitu
  `build_stack_with_market`iin; näin näet selvästi, kuinka paljon
  markkina lisää informaatiota.
* **V2-kehitysideat**:
  * LightGBM LambdaRank oletukseksi ja bayesilainen Laplace-approksimaatio
    koefficienttien luottamusvälien kanssa.
  * Opponent-adjusted rating (nykyinen on heuristinen proxy; todellinen
    ratkaisu olisi iteratiivinen Elo- tai BT-tyylinen päivitys).
  * Online-driftiseuranta (rolling ECE + CUSUM).
  * Train/val -leaker-tarkistin automaattisesti.
  * Pohja poolioptimoinnille: siirrettävissä `toto_optimizer/` -pakettiin
    jo nyt `p_ens`-sarakkeen kautta.

## Vastuullisuus

Tämä on tutkimus- ja analyysityökalu. Hevospelit ovat takeoutin takia
pitkällä aikavälillä negatiivisumma-pelejä; mallin tarjoamat luvut
auttavat realistisemman odotusarvon muodostamisessa, eivät takaa
voittoja. Pelaa vastuullisesti.
