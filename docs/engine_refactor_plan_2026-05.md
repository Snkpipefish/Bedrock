# Engine refactor — 3-fase plan (sub-fase 12.12)

**Triggert av:** `docs/engine_fundamental_review_2026-05-06.md` (10 issues + audit-funn).
**Mål:** løse coordination-layer-issues + forward-data-mismatch + sirkulær score-kalibrering.
**Estimat totalt:** 4-5 uker fokusert arbeid (Fase A + B + C).
**Inkrementell — ikke restart.** Beholder driver-bibliotek, fetcher-infra, bot-integrasjon.

---

## Faseoversikt

| Fase | Effort | Issues løst (av 10) | Leveranser |
|---|---|---|---|
| **A — Coordination layer** | 1-2 dager | 1, 2, 7, 8 | Net-bias filter, cross-horizon dedup, bot risk-cap, horizon-aware entry |
| **B — Forward-data-feeds** | 1 uke | 5 | UNICA estimativa-driver, deficit-revision-feeds, GAIN-parser |
| **C — Empirisk vekt-optimering** | 2-3 uker | 3, 4, 10 | Walk-forward L-BFGS, OOS-floor, k-effective-deflation |

---

## Fase A — Coordination layer (START HER)

### A1: Cross-direction net-bias filter

**Issue:** 16 instrument-horisont-konflikter der BUY+SELL begge over floor.

**Endring:** Ny step i `bedrock/orchestrator/signals.py` etter `_compute_scores`:

```python
def _apply_net_bias_filter(
    entries: list[SignalEntry],
    threshold: float = 1.5,
) -> list[SignalEntry]:
    """For hver (instrument, horizon): hvis |sell - buy| < threshold,
    blokker BEGGE retninger med skip_reason='insufficient_directional_conviction'.
    Ellers: blokker svakeste retning, behold dominerende."""
```

**Konfig:** `config/defaults/orchestrator.yaml` — ny seksjon:
```yaml
net_bias_filter:
  enabled: true
  threshold_default: 1.5
  thresholds_per_asset_class:
    softs: 1.5      # samme som default
    fx: 1.0         # FX trender mer, krever mindre delta
    indices: 1.5
    metals: 1.2
    energy: 1.5
    crypto: 1.0
    grains: 1.5
```

**Tester:** `tests/unit/test_orchestrator_net_bias.py`
- Δ < threshold → begge blokkert
- Δ >= threshold → kun dominant publisert
- Per-asset-class threshold-override fungerer

**Akseptansekriterium:** etter A1, audit `data/signals.json + agri_signals.json` viser 0 instrumenter med BÅDE retninger publisert.

**Filer:**
- Modifiser: `src/bedrock/orchestrator/signals.py`
- Ny: `config/defaults/orchestrator.yaml::net_bias_filter`
- Ny: `tests/unit/test_orchestrator_net_bias.py`

---

### A2: Cross-horizon dedup på setup-nivå

**Issue:** 11 instrumenter publiserer samme retning på flere horisonter med samme entry-level.

**Endring:** Ny step etter `build_setup` i `bedrock/orchestrator/signals.py`:

```python
def _dedup_setups_across_horizons(
    entries: list[SignalEntry],
    entry_diff_pct: float = 0.003,
) -> list[SignalEntry]:
    """Hvis samme (instrument, direction) har flere horisonter med entry-spread
    < entry_diff_pct (0.3%), behold KUN lengste horisont (gir lengst trailing TP).
    De andre markeres skip_reason='subsumed_by_longer_horizon'."""
```

**Konfig:** Samme YAML-blokk:
```yaml
cross_horizon_dedup:
  enabled: true
  entry_diff_pct: 0.003   # 0.3% spread = "samme" entry
  prefer: longest_horizon  # vs highest_score, min_rr_acceptable, etc.
```

**Tester:** `tests/unit/test_orchestrator_horizon_dedup.py`
- Samme instrument+retning, 3 horisonter, samme entry → kun MAKRO publiseres
- Samme instrument, ulike retninger → ingen dedup
- Samme instrument+retning, ulike entries (>0.3% spread) → alle 3 beholdes

**Akseptansekriterium:** etter A2, audit viser maks 1 setup per (instrument, direction) når entries er innenfor 0.3% spread.

**Filer:**
- Modifiser: `src/bedrock/orchestrator/signals.py`
- Ny: `tests/unit/test_orchestrator_horizon_dedup.py`

---

### A3: Bot per-instrument risk-cap

**Issue:** Hvis flere setups for samme instrument blir fylt, summert risk = N × 1%.

**Endring:** `src/bedrock/bot/risk.py`:

```python
def calculate_position_size(
    setup: Setup,
    account_equity: float,
    config: BotConfig,
    open_positions: list[Position],  # NY param
) -> float:
    """...
    Per-instrument risk-cap: hvis open_positions har N andre på samme
    instrument, ny position får (per_instrument_max - sum_existing) / 1.
    """
```

**Konfig:** `config/bot.yaml`:
```yaml
risk:
  per_position_max_pct: 1.0
  per_instrument_max_pct: 1.0    # NY — uavhengig av antall setups
  daily_max_pct: 2.0
```

**Tester:** `tests/unit/test_bot_risk_per_instrument.py`
- 1 setup på Sugar = 1% risk
- 2 setups på Sugar = total 1% (delt)
- 1 Sugar + 1 Coffee = 1% + 1% (separate instrumenter)

**Akseptansekriterium:** bot-state viser at sum(risk_pct for positions per instrument) <= 1.0 til enhver tid.

**Filer:**
- Modifiser: `src/bedrock/bot/risk.py`
- Modifiser: `config/bot.yaml`
- Ny: `tests/unit/test_bot_risk_per_instrument.py`

---

### A4: Horisont-aware entry-distance i setup-builder

**Issue:** Samme entry-level returnert for alle horisonter.

**Endring:** `src/bedrock/setups/generator.py::build_setup`:

```python
HORIZON_MIN_ENTRY_DIST_ATR = {
    Horizon.SCALP: 0.3,    # entry kan være nær current
    Horizon.SWING: 0.7,
    Horizon.MAKRO: 1.5,    # MAKRO krever lengre vei = bedre fill
}

def build_setup(...):
    ...
    min_dist = HORIZON_MIN_ENTRY_DIST_ATR[horizon] * atr
    if abs(entry_level - current_price) < min_dist:
        return None  # ikke "asymmetric setup"
    ...
```

**Tester:** `tests/unit/test_setup_horizon_distance.py`
- MAKRO setup på sukker krever entry > 1.5×ATR fra current
- Hvis closest support er for nær: returnerer None (allerede gjør dette delvis)

**Akseptansekriterium:** MAKRO-setup-entry varierer fra SCALP/SWING-entry når struktur tillater det. Når ikke: MAKRO returnerer None oftere.

**Filer:**
- Modifiser: `src/bedrock/setups/generator.py`
- Ny: `tests/unit/test_setup_horizon_distance.py`

---

### Fase A — Akseptanse

Etter alle 4 sub-tasks:

1. Re-kjør `bedrock signals-all` på alle 22 instrumenter
2. Verifiser:
   - 0 instrumenter med BÅDE retninger publisert (Issue 2 løst)
   - Maks 1 setup per (instrument, direction) på "samme entry-level" (Issue 1 løst)
   - Bot risk-state viser per-instrument-cap aktiv (Issue 8 løst)
   - MAKRO-setups har entry > 1.5×ATR fra current (Issue 7 løst)
3. Snapshot-baseline regenerer (forventet 30-40% færre publiserte signaler totalt)
4. Pyright + pytest grønne
5. Commit-tags: `v0.12.12-fase-a1` ... `v0.12.12-fase-a4`

---

## Fase B — Forward-data-feeds

### B1: UNICA estimativa-driver

UNICA publiserer 2 estimativa-rapporter per år (mai + oktober) med neste-safra-prog. Bygg fetcher som leser disse + ny driver `unica_estimativa_change`.

**Effort:** 3 dager (parser + backfill + driver + tests + wiring).

### B2: Deficit-revision-feeds (Green Pool, Czarnikow, Safras, StoneX)

Disse publiseres ad-hoc ~hver 2. mnd. Bygg fetchers som leser fra:
- Green Pool: nyhetsbrev/blog
- Czarnikow: månedlig market commentary
- Safras: PDF-newsletters
- StoneX: research notes (krever kontoer eller skraping)

**Effort:** 3-4 dager (mest skraping; fanger 2-3 av 4 kilder).

### B3: USDA FAS GAIN-parser

PDF-rapporter for India/Brasil/Thailand sukker, 2-4× per år per land.

**Effort:** 2 dager (PDF-parsing + driver).

### Fase B — Akseptanse

Sukker `unica`-familien får 6-7 drivere (var 5):
- Eksisterende 5 (UNICA cum + USDA + Comtrade)
- + `unica_estimativa_change` (B1)
- + `forecast_revision_z(green_pool|czarnikow)` (B2)
- + `usda_gain_sentiment` (B3, lavere vekt)

Re-kjør backtest v8 — forventet at 180-270d sweet-spot styrkes (markedet handler forward, vi nå også).

---

## Fase C — Empirisk vekt-optimering

### C1: Walk-forward gradient vekt-tuning

Bytt manuelle familie-vekter med data-driven optimering:

```python
def optimize_family_weights(
    instrument: str,
    horizon: Horizon,
    backtest_window: tuple[date, date],
    objective: str = "sharpe",  # eller "calmar", "max_dd_adjusted_return"
) -> dict[str, float]:
    """L-BFGS over familie-vekter, target = annualized Sharpe på rolling 3y.
    Re-kjøres månedlig; YAML-vekter overstyres av kalibrert state-fil."""
```

**Effort:** 1 uke (optimerer + state-management + backtests verify ingen regression).

### C2: Driver-deflate basert på k-effective

Beregn k_effective for hvert instrument:
```
k_eff = total_drivere / (1 + max(intra_family_corr) × n_active_families)
```

Bruk k_eff i grade-thresholds: A+ = top 5% av score-distribusjon (data-driven), ikke fast 10.

**Effort:** 3-4 dager.

### C3: Out-of-sample-only floor-kalibrering

Floor-kalibrering må bruke data som ALDRI har vært brukt til driver-tuning. Splitt:
- 60% drivere-tuning (2012-2023)
- 20% drivere-validering (2024)
- 20% floor-kalibrering (2025-2026)

Re-kalibrer floor månedlig på siste 12 mnd OOS-data.

**Effort:** 1 uke (data-pipeline-omstrukturering + validering).

### Fase C — Akseptanse

- Engine-vekter genereres automatisk per (instrument, horizon, måned)
- Score-distribusjon analysert via k_eff for grade-thresholds
- Floor-kalibrering OOS-only (ingen sirkulær bias)
- Backtest 24-mnd OOS holder >= forrige version på Sharpe + max_dd

---

## Risiko-vurdering

| Fase | Risiko | Mitigering |
|---|---|---|
| A | Lav — endringer i orchestrator + bot, ikke driver-logikk | Snapshot-baseline-diff fanger uventet drift |
| B | Middels — nye fetchers krever ekstern data-stabilitet | Fall-back til None-default ved data-mangel; familie-vekt-trim |
| C | Høy — fundamental endring i kalibrerings-flyt | Kjør parallelt med eksisterende 4-6 uker; cut-over kun etter validering |

---

## Anbefalt cut-over-strategi

**Fase A:** Cut-over umiddelbart etter validering — coordination-fix er ren forbedring uten regress-risiko.

**Fase B:** Cut-over per-driver — wire ny driver med vekt 0.05-0.10 først, øk gradvis basert på faktisk signal-bidrag.

**Fase C:** Build-in-parallel — kjør C1+C2+C3 i shadow-mode 1-2 mnd. Sammenlign signaler side-by-side. Cut-over kun hvis ny systemet er minst like bra som eksisterende på OOS.

---

## Filer å lese ved oppstart

1. `docs/engine_fundamental_review_2026-05-06.md` — issue-katalog
2. `docs/engine_refactor_plan_2026-05.md` (denne) — fase-plan
3. `STATE.md` linje ~100 — sub-fase 12.11+ LUKKET-blokken (kontekst)
4. `src/bedrock/orchestrator/signals.py` — orchestrator-flyt
5. `src/bedrock/setups/generator.py` — setup-builder
6. `src/bedrock/bot/risk.py` — risk-management
7. `config/instruments/sugar.yaml` — kompleksitets-eksempel (5-driver unica-familie)
8. `config/bot.yaml` — bot-konfig

---

*Generert 2026-05-06. Triggeret av sukker-konflikt + fundamental review. Branch: main.*
