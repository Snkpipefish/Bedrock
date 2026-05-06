# BEDROCK Sukker #11 — Peer-review (analytiker-respons)

**Rapport:** Bedrock — Sukker (2026-05-05)
**Analytiker:** Kvant-peer-review
**Format:** Per protokoll (A–E)

---

## A. Sammendrag

Rapporten er metodisk solid på datafundament (14 års pris/COT, 76 års ONI, 12 års UNICA), men har **tre røde flagg** som må fikses før horisont-valg eller floor-rekalibrering har mening:

1. **Ikke-monoton SELL-progresjon** (A SELL 32.0 % hit / −3.51 %; B SELL 39.6 % / +2.06 %). Dette er ikke et grade-cutoff-problem — det er et signal om at ekstrem-grade SELL fanger *overshoots som mean-reverter*. Må løses før noe annet kalibreres.
2. **Korrelerte familier dobbelt-vektet**. `outlook` (5) og `unica` (2) måler i praksis samme akse (Brasil-sesong/produksjon). Effektiv vekt på Brasil-sesong ≈ 7/16 = 44 %. Det er for mye.
3. **Multiple-testing-eksponering ignorert**. 4 horisonter × 2 retninger × 4 grader = 32 tester. Krever DSR (deflated Sharpe) eller minimum Bonferroni før noen "edge"-konklusjon publiseres.

A+ BUY på 90d (44.6 % hit, +4.69 % avg) ser ekte ut, men trenger DSR-deflasjon før det går i produksjon.

Strukturell SELL-bias er empirisk reell, men `floor=5` er aggressivt — re-kalibrering må gjøres på rullerende vindu, ikke statisk 14-års-snitt.

---

## B. Svar per spørsmål

### A) Familievekter — fordeling er feil, total er rett

**Svar:** Total 16 beholdes, men fordelingen rebalanseres.

| Familie | Nå | Forslag | Begrunnelse |
|---|---:|---:|---|
| outlook | 5 | **3** | Korrelert med `unica`. Sesong er kjent priori — marginal info er lavere enn taket impliserer. |
| yield | 3 | **3** | Beholdes. |
| **positioning** | **2** | **4** | COT er den enkeltsterkeste signal-kilden i softs. n=852 ukerap støtter høyere vekt. Z-score + OI-flow + swap-skew = tre uavhengige sub-signaler. |
| enso | 2 | 2 | Beholdes. ONI har 76 års historikk men slow-moving — taket bør ikke økes. |
| unica | 2 | 2 | Beholdes, men flag korrelasjon med outlook. |
| cross | 2 | 2 | Beholdes. |
| analog | 2 | **0** | K-NN på softs er typisk lav-signal og høy-overfit. Drop til ablation viser ekte bidrag. |
| **Total** | 16 | **16** | |

**Implementering:** kjør ablation-test (drop én familie ad gangen, mål Sharpe-tap på A+ BUY 90d-bøtten). Familier som ikke gir > 0.15 Sharpe-tap bør tak-reduseres, ikke beholdes ut fra domene-intuisjon.

**Validering:** sammenlign baseline (nåværende vekter) mot forslag på samme walk-forward-vindu. Suksess-kriterium: ≥ 10 % Sharpe-løft på A+ BUY uten signifikant tap på SELL-grenen.

---

### B) Asymmetrisk publish-floor — ikke re-kalibrer ennå, gjør det riktig

**Svar:** Nei på umiddelbar re-kalibrering. Først fiks non-monotonisitet i SELL-grader (se A.1).

**Begrunnelse:**
- Backtest-perioden 2010–2026 dekker to regimer: oversupply 2017–2020 (BR rekord) og shortage-press 2023 (India-forbud). Statisk 14-års-floor antar regime-stasjonaritet.
- Strukturell SELL-bias er reell (HFCS-substitusjon, BR-kapasitet), men varierer med BRL-regime og India-policy. Når BRL styrker seg + India eksporterer, snur bias.
- BUY n=489 vs SELL n=489 er greit utvalg, men hit-rate-forskjellen 34.9 % vs 45 % er innenfor rimelig regime-varians.

**Implementering:**
- Bytt fra statisk floor til **rullerende 5-års-empirisk floor**, oppdatert kvartalsvis.
- Floor settes der historisk grade-grense gir ≥ 55 % hit-rate i den retningen, gitt nåværende regime.
- Hold buy=7, sell=5 som **prior**, men la rolling-window overstyre.

**Validering:** out-of-sample test på 2023–2026 (India-forbud-regime) — sjekk om dynamisk floor unngikk de store SELL-tapene som statisk floor ville tillatt.

---

### C) Seasonal_stage — JA, redesign til forward-syklus

**Svar:** Sterk anbefaling om redesign. Nåværende current-cycle-logikk er metodisk feil for et forward-priset marked.

**Begrunnelse:**
- Forward-curve viser pris-discovery for neste safra starter 6–12 mnd før zafra-start. Mai-2027-kontrakten priser inn 2027/28-safra fra ca. mai-2026.
- Når mølla starter crush i april, er prisen *allerede* satt på forventning. Dvs. peak-bull-window er **før** zafra, ikke under den.
- Dagens score peak (mai–aug = 1.0) fanger opp lager-bygging, ikke pris-discovery.

**Foreslått forward-syklus mapping (J–F–M–A–M–J–J–A–S–O–N–D):**
```
[1.0, 1.0, 0.9, 0.7, 0.6, 0.7, 0.8, 0.9, 1.0, 0.9, 0.8, 0.9]
```

Logikk:
- **Jan–feb (1.0)**: Entressafra slutter, neste-safra-usikkerhet høyest, vær-volatilitet inn i monsun (India) og pre-zafra (BR).
- **Mar–mai (0.7–0.9)**: Zafra-start fjerner usikkerhet, lager bygges → bear-bias.
- **Jun–aug (0.7–0.9)**: Frost-vindu kan re-prise, men hovedsupply allerede synlig.
- **Sep–okt (0.9–1.0)**: Zafra-topp = peak supply-press, men også start på prising av neste år.
- **Nov–des (0.8–0.9)**: Entressafra kommer, lager-trekk starter.

**Implementering:** kjør begge versjoner parallelt i 2 kvartaler. A/B-test på A+ BUY hit-rate.

**Validering:** forward-syklus skal gi høyere score-utslag i feb–mar enn current-syklus. Hvis ikke, er driver-implementasjonen feil.

---

### D) Multi-region weather — JA, men vekt etter eksport-impact, ikke produksjon

**Svar:** Bygg multi-region. Foreslått 0.6/0.25/0.15-vekting er feil — basert på total produksjon.

**Begrunnelse:**
- Sukker-pris drives av **eksport-tilgjengelighet**, ikke total produksjon. Kina produserer ~10 mt og eksporterer null. India produserer 35 mt men eksporterer 0–10 mt avhengig av politikk.
- Brasil dominerer eksport (~45 % av globalt eksport-volum), ikke 60 % av produksjon.
- India er **policy-swing-faktor**: når de eksporterer eller forbyr, beveger pris 200–300 bps. Vær påvirker monsun → produksjon → policy → eksport. Mer høy-leverage enn Thailand.

**Foreslått vekting (eksport-impact-justert):**
```
Centro-Sul: 0.55  (dominerer eksport, men BR vær-data alt diskontert)
India:      0.30  (høy beta på policy-overgang, monsun = inngangs-driver)
Thailand:   0.15  (jevn eksportør, mindre vær-leverage på pris)
```

**Implementering:**
- India-vær: IMD-data (gratis), monsun-progresjon vs LPA. Maharashtra + UP = 60 % av nasjonal produksjon — bruk regional, ikke nasjonal aggregering.
- Thailand: TMD eller ECMWF reanalysis-data.
- Aggregér som vektet z-score, ikke vektet rå-stress (z-score gjør regioner sammenlignbare på tvers av klima).

**Validering:** kjør 2023-India-forbud-perioden isolert. Multi-region weather-driver bør ha gitt SELL-signal-svekkelse i Q2–Q3 2023 (monsun under LPA → policy-risiko bygges).

---

### E) Etanol-paritet — JA, drop crude-proxy umiddelbart

**Svar:** Bygg dedikert `ethanol_parity_brl`-driver. Crude er metodisk svak proxy.

**Begrunnelse:**
- Crude → BR etanol-pris går gjennom: Petrobras-prising (politisk styrt), BR-skattestruktur, BRL-FX, regionale logistikkostnader. Tre ledd som decouple-r.
- ANP publiserer daglig hydrous og anhydrous etanol-pris gratis — direkte måling.
- Sukker/etanol-switch er den eneste virkelige short-run-supply-mekanismen i BR. Direkte måling er ikke "nice to have" — det er kjernedriveren.

**Implementering (skissert):**
```
paritet_cents_lb = (anhydrous_brl_per_liter / brl_usd_rate)
                 × (1 / kg_sugar_per_liter_etanol_equiv)
                 × (lb / kg) × 100

signal = (paritet_cents_lb - sb_front_settle) / ATR_20d
```

- `kg_sugar_per_liter_etanol_equiv` ≈ 1.852 (industri-standard, kan kalibreres mot UNICA mix-data).
- Når signal > 0 (etanol mer attraktivt enn sukker), mølle-allokering skifter fra sukker → etanol → bullish #11. Sterkest når signal > +1σ over 60d.

**Validering:** korrelasjon mellom `ethanol_parity_brl`-signal og UNICA neste-rapport mix_sugar_pct. Forventet: |ρ| > 0.5 negativ (høy paritet → lavere sukker-mix). Hvis < 0.3, er driver-formelen feil.

---

### F) Manglende data — prioritert ROI

**Rangering (Sharpe-løft per arbeidsdag):**

| Kilde | ROI | Innsats | Begrunnelse |
|---|---|---|---|
| **ANP etanol** | Høyest | 1 dag | Direkte input til kjernedriveren, gratis daglig data. |
| **ISMA India** | Høy | 2–3 dager | India er største policy-swing-faktor. Månedlig produksjon + eksportkvote. |
| **CONAB Brasil** | Høy | 2 dager | Cross-validering UNICA, kvartalsvis offisiell balanse. |
| **CEPEA/ESALQ** | Middels | 1 dag | Physical-premium-signal, fanger basis-divergens vs futures. |
| **OCSB Thailand** | Middels | 2 dager | Bekrefter alternate-supply, mindre prisleverage enn India. |
| **USDM India/Thailand** | Lav | 3–5 dager | Allerede delvis fanget i monsun-proxy + IMD. Marginal info. |
| **MAPA** | Lav | 3 dager | Overlapper CONAB. Hopp over til CONAB er etablert. |

---

## C. Metodiske innvendinger

### C.1. Ikke-monoton SELL-grade-progresjon (kritisk)

A SELL: hit 32.0 %, avg −3.51 %. B SELL: hit 39.6 %, avg +2.06 %.

Dette er **ikke** "inkonsistent grade-progresjon" — det er sannsynligvis et reelt mønster: ekstrem-grade SELL-signaler fanger *posisjons-overshoots* som mean-reverter. Klassisk eksempel: COT MM netto-short −3σ → kontrært BUY-setup, ikke SELL-bekreftelse.

**Løsning:**
- Driver-attribution per grade-bøtte. Hvilken familie dominerer A SELL-graden? Hvis det er `positioning` med ekstrem MM-short, må direksjonalitets-logikken (ADR-006) revurderes for den familien.
- Vurder `positioning`-flip: ved z-score < −2.0, signaler bør ha REDUSERT vekt eller motsatt fortegn (mean-reversion-modus).

### C.2. Korrelerte familier

`outlook` (seasonal_stage) og `unica` (sugar_production_yoy + mix_sugar_pct) deler informasjons-akse: BR-sesong/produksjon. Effektiv eksponering 7/16 = 44 % er for høy.

**Løsning:** beregn parvis driver-korrelasjon på 14 års data. Familier med ρ > 0.6 bør konsolidere tak eller bruke residualisert versjon.

### C.3. Manglende multiple-testing-korreksjon

32-test-rute (4h × 2dir × 4grade) krever DSR. Med α=0.05 og 32 tester gir Bonferroni krav om p < 0.0016 per test for genuin signifikans.

**Løsning:** López de Prado DSR med antall trials = 32. Rapporter PSR (Probabilistic Sharpe Ratio) ved siden av rå hit-rate.

### C.4. n=3 i B BUY

0.0 % hit-rate på n=3 er ikke et resultat — det er støy. Krev minimum n=30 per grade-gren før konklusjon. Inntil da: lump B BUY inn med A BUY eller marker som "insufficient data".

### C.5. h=180 ga ingen outcomes

Hvis ingen outcomes = look-ahead-vinduet stikker utover datasettet. Ikke "manglende signal", men ekskluderingsregel som spiste alle observasjoner. Sjekk hvorfor — sannsynligvis krever 180d-vindu observasjoner før 2023-08 for å ha realisert outcome, og data-cutoff har ekskludert de.

---

## D. Prioritert tiltaksliste (rangert etter Sharpe-løft per dag)

| # | Tiltak | Dager | Forventet løft | Risiko hvis ignorert |
|---:|---|---:|---|---|
| 1 | **Driver-attribution A SELL** + fiks non-monotonisitet | 2 | Høy | Hele SELL-grenen er upålitelig |
| 2 | **ANP etanol-paritet-driver** erstatter crude-proxy | 1 | Høy | Kjerne-driver feilspesifisert |
| 3 | **Forward-syklus seasonal_stage** redesign | 1 | Høy | Outlook-familien jobber mot prisen |
| 4 | **DSR + Bonferroni** på 32-test-rute | 1 | Middels | Falske edge-konklusjoner |
| 5 | **ISMA India**-integrasjon | 2–3 | Høy (regime-betinget) | Blind for største policy-swing-faktor |
| 6 | **Familie-vekt-rebalansering** (ablation-drevet) | 2 | Middels | Suboptimal aggregering |
| 7 | **Multi-region weather** (eksport-impact-vektet) | 4–5 | Middels | Globale supply-shocks underreagert |
| 8 | **Rullerende 5-års publish-floor** | 1 | Lav umiddelbart, høy ved regime-skift | Statisk floor feiler ved regime-overgang |
| 9 | **Horisont-bekreftelse** etter pågående 4h-backtest | 0 (venter) | — | Allerede i pipeline |

**Sannsynligvis bortkastet tid:** USDM India/Thailand drought (info allerede fanget), MAPA (overlapper CONAB), ekspanderende `analog`-familie (lav-signal, høy-overfit).

---

## E. Validerings-plan

| Endring | Test | Suksess-kriterium |
|---|---|---|
| Driver-attribution A SELL | Per-grade-bøtte familie-bidrag på 2010–2026 | Identifiser hvilken familie driver 32.0 % hit-rate; løsning skal gi monoton progresjon A > B > C |
| ANP etanol-paritet | Korrelasjon driver-signal vs UNICA neste-rapport mix_sugar_pct | \|ρ\| > 0.5 negativ |
| Forward-syklus | Walk-forward 2018–2026 vs nåværende current-cycle | Sharpe-løft ≥ 0.20 på outlook-familien isolert |
| DSR | Beregn over 32-test-rute | A+ BUY 90d skal beholde p < 0.05 etter deflasjon |
| ISMA India | OOS 2023 (India-forbud) | India-driver skal ha gitt advarsel-signal Q1–Q2 2023 |
| Familie-rebalansering | Ablation drop-one-out | Drop av familie skal koste ≥ 0.15 Sharpe; ellers reduser tak |
| Multi-region weather | OOS 2023-monsun-svikt-perioden | Driver skal flippe SELL → nøytral i Q2 2023 |
| Rullerende floor | OOS 2023–2026 | Dynamisk floor skal blokkere SELL-publish under India-forbud-regime |

---

## Avsluttende merknad

Datafundamentet er solid nok til å fortsette. Kritisk sti: **fiks non-monotonisitet i SELL først** (tiltak 1), deretter ANP etanol-paritet (tiltak 2) og forward-syklus (tiltak 3). Disse tre tar ~4 dager kombinert og adresserer de tre svakhetene som ellers vil korrumpere all videre kalibrering.

Re-kalibrering av publish-floor og horisont-valg bør **vente** til SELL-grenen er metodisk korrekt — ellers kalibrerer du på et signal som er feilspesifisert.
