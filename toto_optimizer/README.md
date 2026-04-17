# Toto Optimizer

Tuotantotasoinen Python-paketti, joka

1. **lataa** Veikkauksen Toto-lähtöjen data (CSV/JSON/demo),
2. **rakentaa** pehmeät, kilpailunsisäisesti z-skaalatut piirteet,
3. **estimoi** hevoskohtaiset voittotodennäköisyydet Plackett-Luce / softmax -mallilla ja kalibroi ne isotonisella regressiolla,
4. **debias-aa** Veikkauksen pelaajapoolin osuudet Shin-menetelmällä,
5. **yhdistää** mallin ja markkinan log-lineaarisella ensemblellä,
6. **tunnistaa ali- ja ylipelatut** hevoset ja yhdistelmät,
7. **optimoi** pelirivit kolmella strategialla (max osumatn., max EV, jackpot-uniikkius),
8. **simuloi** pitkän aikavälin tuoton Monte Carlo -menetelmällä,
9. tarjoaa **Streamlit-UI:n** ja CLI:n.

> **Vastuunrajaus.** Paketti on analyysityökalu. Se ei lupaa voittoja eikä ennusta lopputuloksia varmasti. Käytettäessä oikean rahan panoksiin vastuu on aina pelaajalla. Paketti on suunniteltu toimimaan Veikkauksen käyttöehtojen puitteissa: se ei hae dataa suoraan Veikkauksen sivuilta, vaan lukee datan CSV- tai JSON-syötteenä (tai käsin syötetystä UI-kentästä).

---

## Asennus

```bash
cd toto_optimizer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.10+ vaaditaan.

## Käyttö

### Demo-ajo (synteettinen data)

```bash
python -m toto_optimizer.app.main demo \
    --product toto75 --budget 20 \
    --strategy jackpot --jackpot 250000 --pool 500000
```

### CSV-datan ajaminen

```bash
python -m toto_optimizer.app.main run \
    --card toto_optimizer/data/sample/sample_toto75.csv \
    --pool-shares toto_optimizer/data/sample/sample_pool_shares.csv \
    --product toto75 --jackpot 250000 --pool-eur 500000 \
    --budget 20 --strategy jackpot
```

### Streamlit-käyttöliittymä

```bash
streamlit run toto_optimizer/app/ui.py
```

Käyttöliittymässä voit
- ladata CSV/JSON-datan tai käyttää demo-dataa,
- asettaa jackpotin, poolin koon, takeoutin, budjetin, rivin hinnan,
- säätää strategian ja jackpot-painotuksen gamman,
- tarkastella fair odds -kertoimia, edge-lukuja ja rivisuosituksia perusteluineen,
- simuloida rivien pitkän aikavälin tuoton.

## Projektin rakenne

```
toto_optimizer/
├── app/                  # CLI + Streamlit UI + config
├── data/                 # Pydantic-skeemat, latausfunktiot, sample-data
├── features/             # Feature engineering
├── models/               # Plackett-Luce, kalibrointi, ensemble
├── pool/                 # Markkina-/poolimalli (Shin-debias, combo-popularity)
├── optimizer/            # Tavoitefunktiot + rivigeneraattori
├── simulation/           # Monte Carlo -simulaatio
├── tests/                # pytest-testit
├── requirements.txt
└── README.md
```

## CSV-skeema (lähtörivi)

Pakolliset sarakkeet:

| sarake | tyyppi | kuvaus |
|--------|--------|--------|
| `race_id` | string | yksilöivä lähtötunniste (esim. "R1") |
| `race_number` | int | lähdön järjestysnumero |
| `track` | string | rata |
| `distance_m` | int | matka metreinä |
| `program_number` | int | hevosen ohjelmanumero |
| `name` | string | hevosen nimi |

Valinnaiset sarakkeet (käytetään mallissa jos annettu):

`start_type` (volt/auto/flying), `race_class`, `driver`, `trainer`,
`post_position`, `speed_rating`, `class_rating`, `stamina_rating`,
`gallop_risk` (0-1), `days_since_last_start`, `equipment_change` (bool),
`shoeing_change` (bool), `pool_percentage` (0-100), `published_odds`,
`recent_finishes` (pipe-separoitu, `"1|2|4|3|5"`),
`recent_kilometer_times` (pipe-separoitu), `recent_earnings`,
`finished_position` (historialliselle datalle), `did_not_finish`.

Pool-jakauman CSV:

| sarake | tyyppi |
|--------|--------|
| `race_id` | string |
| `program_number` | int |
| `share` | float (0-1 tai 0-100) |

## Matemaattiset perustelut

### Voittotodennäköisyys (Plackett-Luce / softmax)

Hevoselle `i` lähdössä lasketaan vahvuus λ_i = exp(βᵀx_i). Voittotodennäköisyys on

```
P(i voittaa) = λ_i / Σ_j λ_j
```

jonka ansiosta todennäköisyydet summautuvat tasan yhteen. β estimoidaan
maksimoiden log-likelihoodia `Σ log P(winner_r | β)` yli lähtöjen r, ja
L2-ridge-rangaistus `(λ/2)‖β‖²` vakauttaa fitin. Ilman historiadataa
käytetään priori-β:aa, joka koodaa yleisesti päteviä vaikutussuuntia.

### Kalibrointi

Isotonic regression oppii monotonisen kuvauksen raa’an ennustetun
todennäköisyyden ja todellisen voittofrekvenssin välillä. Kalibroitu
vektori normalisoidaan uudelleen lähtökohtaisesti niin, että summa on 1.
Mittarit: Brier = `mean((p - y)²)`, log-loss = `-mean(y log p + (1-y) log(1-p))`,
ECE = ryhmien painotettu keskiero ennustetun ja havaitun välillä.

### Fair odds

```
fair_odds_i = 1 / p_i
```

Marginaalikorjattu turvakerroin: `1 / (p_i * (1+m))`, missä `m` on haluttu
turvamarginaali.

### Poolin implikoima todennäköisyys (Shin 1993)

Havaitut poolin osuudet `q_i` normalisoidaan ja ratkaistaan `z ∈ (0,1)` yhtälöstä

```
Σ_i (√(z² + 4(1-z) q_i²) - z) / (2(1-z)) = 1
```

Debiasattu implikoitu tn. on

```
π_i = (√(z² + 4(1-z) q_i²) - z) / (2(1-z))
```

Tämä vetää massaa suosikeilta kohti pitkäveton hevosia ja poistaa
favourite-longshot-biaksen.

### Edge

```
edge_i = p_model_i / π_market_i
log_edge_i = log(edge_i)
```

`edge > 1` = alipelattu, `edge < 1` = ylipelattu.

### Rivin odotusarvo

Olkoon yhdistelmälle c osumatodennäköisyys `P_hit(c) = Π_k p_leg[k][c_k]` ja
pooli-suosio `π(c) = Π_k s_leg[k][c_k]`. Kun `N_other` on vastustajarivien
määrä, odotetusti voittaviin rivien lukumäärä jaettuna yhdellä on
`1 + N_other · π(c)`. Prize pool = `(1 - takeout) · pool + jackpot`. Tällöin

```
EV(c) = P_hit(c) · prize_pool / (1 + N_other · π(c)) - stake_unit
```

### Uniikkius ja jackpot-objektiivi

```
uniqueness(c) = 1 / (1 + N_other · π(c))
jackpot_score(c) = EV(c) · uniqueness(c)^γ
```

Kun γ = 0 saadaan puhdas EV-optimointi. Suurella γ (esim. 1-2) järjestelmä
suosii erottuvia yhdistelmiä, mikä on erityisen arvokasta kun jackpot on
iso ja yksinäinen voittaja vie suurimman osan pooleista.

### Rivien valinta

Jokainen lähtö rajataan N parhaaseen (`top_k_per_leg`), minkä jälkeen
yhdistelmät generoidaan Cartesian-tulolla (pienet avaruudet) tai beam
searchilla (suuret avaruudet). Yhdistelmät pakataan ahneella algoritmilla
"harava"-systeemeihin, joissa systeemin laajentaminen hyväksytään vain
jos marginaali-EV paranee ja budjetti ei rikkoudu.

## Testit

```bash
pytest toto_optimizer/tests -q
```

## Oletukset ja rajoitteet

- **Takeout** oletetaan 25 %:ksi, ellei sitä tarkenneta. Todellinen takeout
  vaihtelee tuoteperheittäin (Toto-75, Toto-76, Toto-4 jne.).
- **Opponent-tickets** estimoidaan heuristiikalla `pool_eur / stake_unit`,
  kun tarkkaa rivimäärää ei tunneta.
- **Chalk correlation** (`MarketModel(chalk_correlation=…)`) on
  yksinkertainen approksimaatio; todellinen rivien korreloituminen pitäisi
  kalibroida historiadatasta.
- **Prior-β** on käytössä silloin kun historiadataa ei ole. Priorit ovat
  konservatiivisia eivätkä korvaa kunnollista kalibraatiota.
- **Plackett-Luce yhden voittajan muodossa** – pakettia ei ole tehty
  pareto/trifecta-tyyppisten monipaikkaennusteiden alkuperäiseen muotoon.
- **Ei scrapingia** – Veikkauksen sivuilta ei haeta dataa suoraan.

## Jatkokehitysehdotukset

1. **Oikea datalähde** – toteuta `RaceCardLoader`-protokolla Veikkauksen
   virallista API:a / tietolähdettä vasten (käyttöehtojen sallimalla tavalla).
2. **Historiamalli** – kerää muutaman tuhannen lähdön historia ja kalibroi
   `train_from_history` -pipeline uudelleen säännöllisesti.
3. **Gradient boosting -ensemble** – lisää LightGBM-pohjainen malli
   ja yhdistä se LogLinearEnsemble-luokkaan.
4. **Bayesilainen epävarmuusarvio** – korvaa point-estimaatti MCMC:llä
   (pymc) tai Laplace-approksimaatiolla ja tulosta luottamusvälit.
5. **Rivirakenne-optimointi** – korvaa greedy-systeemipakkaus
   MILP-ratkaisijalla (PuLP/CBC), joka maksimoi portfolio-EV:n yhtenä
   integer-ongelmana.
6. **Kalibrointimonitorointi** – online-Brier/ECE-mittarit ja driftin
   havaitseminen.
7. **Rivisuosiokorjaus** – kalibroi chalk-korrelaatio aidolla
   rivisuosiodatalla.

## Lisenssi

MIT. Paketti on koulutus- ja tutkimustarkoituksiin.
