# Hva skjedde med Bunke 3/4/7 — wiring-status og uføyelser

Sub-fase 12.10 hovedlevering (LUKKET 2026-05-02, tag `v0.12.10-fase-12.10-LUKKET`)
leverte 9 bunker som registrerte ~50 nye drivere + utførte ~60 000 nye datarader
i backfill, men i tråd med PLAN § 22.1 (2026-05-02 låst):

> **§ 22.1: live-demo-validering først, så utvide.** YAML-wiring av nye drivere
> deferres til Spor A (follow-up) for å holde grade-distribusjons-impact
> kontrollert per asset-class.

Det vil si: drivere ble *implementert* og *backfilt* i bunkene, mens *YAML-wiring*
ble lagt til Spor A1-A11 etterpå. Dette forklarer hvorfor noen bunke3/4/7-drivere
fortsatt står "registrert men ikke wired" — de ble ikke prioritert i Spor A-runden.

## Bunke 3 (FRED-utvidelse) — 14 drivere registrert

| Driver | Wired? | Hvor / hvorfor ikke |
|---|---|---|
| `t10y3m` | ✅ | A5 → SP500/Nasdaq macro |
| `hy_oas_change` | ✅ | A7 → SP500/Nasdaq risk |
| `initial_claims_z` | ✅ | A8 → SP500/Nasdaq macro |
| `industrial_production_yoy` | ✅ | A8 → SP500/Nasdaq macro |
| `jolts_openings_yoy` | ✅ | A10 → SP500/Nasdaq macro |
| `m2_yoy` | ✅ | A5 → SP500/Nasdaq macro |
| `anfci_z` | ✅ | A10 (erstattet `nfci_change`) |
| `vix9d_vix_ratio` | ✅ | A1 → SP500/Nasdaq risk |
| `dollar_index_breadth` | ✅ | A3 → EURUSD/GBPUSD/USDJPY/AUDUSD macro |
| `cfnai_3mma` | ❌→✅→❌ | A10 → SP500/Nasdaq macro, **deretter erstattet av `ism_pmi_level` i F1** (2026-05-02) |
| `umich_sentiment_z` | ❌→✅→❌ | Wired tidligere, **erstattet av `treasury_auction_demand` i F6** (2026-05-02) |
| `nfci_change` | ❌ | **Erstattet av `anfci_z` i A10** før wiring; permanent ubrukt |
| `t_bill_3mo_yield` | ❌ | Aldri wired — `t10y3m` (yield-curve) dekker rate-signal, T-bill-level alene mindre actionable |
| `continuing_claims_z` | ❌ | Aldri wired — `initial_claims_z` dekker labor-stress; CCSA er etterskudds-signal som duplikerer ICSA |
| `fomc_decision_distance` | ❌ | Aldri wired — `event_distance` (calendar_ff) dekker generell event-timing inkludert FOMC |
| `ism_pmi_level` | ✅ | F1 (2026-05-02) — manuell CSV-fallback (FRED NAPMPMI er 404) |

**Ubrukt-status:** 5 av 14 ikke wired (`cfnai_3mma`, `umich_sentiment_z`,
`nfci_change` ble erstattet; `t_bill_3mo_yield`, `continuing_claims_z`,
`fomc_decision_distance` redundant med eksisterende drivere).

## Bunke 4 (Yahoo + CBOE + NOAA) — 8 drivere registrert

| Driver | Wired? | Hvor / hvorfor ikke |
|---|---|---|
| `move_index_z` | ✅ | A1 → indices risk |
| `vvix_z` | ✅ | A2 → indices risk |
| `gvz_z` | ✅ | A1 → Gold macro |
| `ovx_z` | ✅ | A1 → CrudeOil/Brent macro |
| `cboe_skew_z` | ✅ | A1 → indices risk |
| `noaa_oni_index` | ✅ | A4 (erstattet `enso_regime` på 7 agri-instrumenter) |
| `noaa_pdo_index` | ❌ | Aldri wired — multi-decade-pattern, mer "interessant" enn actionable for 1-30d-trade-horisont |
| `intraday_atr_h1` | ❌ | Aldri wired — krever H1-data i `prices`-tabell som vi ikke fetcher (kun D1) |
| `noaa_enso_forecast_3mo` | ✅ | F4 (2026-05-02) — manuell CSV-fallback |

**DEFERRED:** `cboe_pcr_total_extreme`, `cboe_pcr_equity_only`,
`cboe_vix_term_curve`. F3 droppet `cboe_vix_term_curve` (overlapper
`vix_term_ratio`); F2 re-deferred PCR-driverne (CBOE paywalled DataShop).

**Ubrukt-status:** 2 av 8 (`noaa_pdo_index` lav verdi, `intraday_atr_h1`
trenger H1-data).

## Bunke 7 (GIE + COT-disaggregated) — 7 drivere + 4 (Spor C/F5)

| Driver | Wired? | Hvor / hvorfor ikke |
|---|---|---|
| `agsi_germany_pct` | ✅ | A3 → NaturalGas macro |
| `agsi_netherlands_pct` | ✅ | A3 → NaturalGas macro |
| `agsi_italy_pct` | ✅ | A9 → NaturalGas macro |
| `agsi_withdrawal_rate` | ✅ | A9 → NaturalGas macro |
| `agsi_injection_rate` | ✅ | A11 → NaturalGas macro |
| `cot_oi_change` | ❌ | Aldri wired — `cot_z_score` dekker primær COT-signal |
| `cot_commercial_extreme` | ❌ | Aldri wired — overlapper med `cot_z_score` (begge måler MM-positioning-ekstremitet, bare via ulik tilnærming) |
| `alsi_eu_pct` | ✅ | C5 → NaturalGas macro |
| `alsi_storage_change` | ✅ | C5 → NaturalGas macro |
| `iip_supply_unavailability` | ✅ | C5 → Brent + NaturalGas macro |
| `cot_concentration_top4` | ✅ | F5 (2026-05-02) → Gold + CrudeOil positioning |
| `cot_swap_dealer_skew` | ✅ | F5 (2026-05-02) → Gold + CrudeOil positioning |

**Ubrukt-status:** 2 av 12 (`cot_oi_change`, `cot_commercial_extreme` —
begge overlapper eksisterende COT-driver).

## Hvorfor disse aldri ble wired — root cause

Spor A1-A11 ble drevet **opportunistisk per asset-class**, ikke
**systematisk per driver**. Operatør og Claude wired drivere som ga klar
incremental verdi for hovedinstrumenter (SP500/Nasdaq/CrudeOil/NaturalGas/Gold).
13 drivere falt mellom (a) "redundant med eksisterende" eller (b)
"trenger en data-kilde vi ikke fetcher" (intraday_atr_h1).

Ingen feil i prosessen — alt ble levert teknisk, men wiring-strategien
var verdi-drevet, ikke fullstendighet-drevet.

## Anbefaling for de 13 ubrukte driverne

| Driver | Anbefalt handling |
|---|---|
| `cfnai_3mma`, `umich_sentiment_z`, `nfci_change` | **DELETE** — erstattet av bedre alternativer i F1/F6/A10 |
| `enso_regime` | **HOLD** — brukes av analog-modul (dim-extractor); refactor er egen mini-spor |
| `cot_oi_change`, `cot_commercial_extreme` | **HOLD eller DELETE** — vurder om de gir uavhengig signal vs `cot_z_score` på live-demo-data; flag for Spor E |
| `noaa_pdo_index` | **HOLD** — multi-decade-pattern kan bli relevant ved spesifikk regime-spørring |
| `intraday_atr_h1` | **HOLD** — venter på H1-prices-fetch hvis SCALP-cadence krever det |
| `t_bill_3mo_yield`, `continuing_claims_z`, `fomc_decision_distance`, `vix_term_ratio` | **DELETE** — redundant med eksisterende drivere |
| `news_intel_severity_veto` | **HOLD** — hard-veto-driver krever bevisst aktivering med policy-grenser |

Anbefales å revurdere ved Spor E-åpning ~2026-06-01 (etter live-demo-empiri).

---

## Bonus: agsi/alsi/iip/aaii oppdaterings-mekanismer (audit-oppfølging)

| Tabell | Siste rad | Driver wired? | Oppdaterings-mekanisme |
|---|---|---|---|
| `agsi_storage` | 2026-04-27 (5d) | ✅ 5 drivere | **MANGLER daglig timer** — kun manuelt via `scripts/backfill/agsi.py` |
| `alsi_storage` | 2026-04-30 (2d) | ✅ 2 drivere | **MANGLER daglig timer** — kun manuelt via `scripts/backfill/alsi.py` |
| `iip_remit` | 2026-05-02 (0d) | ✅ 1 driver | **AKTIV** — får 7-16 nye rader/dag fra et eller annet sted (sannsynlig kjørt manuelt eller via en mekanisme utenfor user-systemd) |
| `aaii_sentiment` | 2026-04-30 (2d) | ✅ 1 driver | **MANGLER daglig timer** — ukentlig kadens, akseptabelt med manuell |

### Anbefaling
- **agsi + alsi:** registrér som runners i `fetch.yaml` (daglig 06:00 Oslo
  etter GIE D+1 publisering). Krever `@register_runner("agsi")` og
  `@register_runner("alsi")` i `fetch_runner.py` + cron-entries. Driverne
  i NaturalGas leser allerede tabellene; manglende fersk data svekker
  signalet uten advarsel.
- **iip:** sjekk hvor det daglige fetch-jobben kjører fra (er den manuell?
  hvis så, registrer som runner for å gjøre den robust).
- **aaii:** ukentlig (Mandag), kan registreres med cron `0 9 * * 2`
  (tirsdag morgen etter AAII-Sentiment-Survey-publisering torsdag, 5d
  buffer).
