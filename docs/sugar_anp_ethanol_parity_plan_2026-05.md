# Sugar ANP etanol-paritet — implementerings-skisse

**Status:** Skissert, ikke implementert. Estimert 1 dag arbeid.
**Trigger:** Analytiker-anbefaling D.2 (peer-review 2026-05-05).
**Erstatter:** `momentum_z` på CrudeOil (cross-familie weight 0.20) — metodisk svak proxy.

## 1. Datakilde

**ANP (Brasil olje- og gass-regulator)** publiserer ukentlig pumpepris for ETANOL (hydrous), GASOLINA og GASOLINA ADITIVADA per delstat per revenda (gasstasjon).

- Format: månedlige CSV-filer, 16 kolonner, ~7 MB hver
- URL-mønster: `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/{YYYY}/{MM}-dados-abertos-precos-gasolina-etanol.csv`
- Hyppighet: månedlig publisering (ca 5. i mnd, dekker forrige måneds ukentlige innsamlinger)
- Fra: 2004 → nå
- Auth: ingen (offentlig dataset)

## 2. Bedrock-integrasjon

### 2.1 Fetcher
`src/bedrock/fetch/anp_ethanol.py`

```python
def fetch_anp_ethanol_weekly(from_date: date, to_date: date) -> pd.DataFrame:
    """Returnerer aggregert ukentlig snittpris per delstat for ETANOL.

    Steg:
    1. For hver måned i vinduet: GET månedlig CSV
    2. Filter Produto = 'ETANOL'
    3. Filter Estado i CENTRO_SUL_STATES (SP, GO, MG, MT, MS, PR, RJ, ES)
    4. Konverter brasiliansk pris ('5,99' R$/litre) til float
    5. Aggregér: avg(Valor de Venda) per (uke, delstat)
    6. Vekt etter eksport-impact (SP=0.55 dominerer):
       Centro-Sul-snitt = SP*0.45 + GO*0.15 + MG*0.15 + MS*0.10
                        + MT*0.10 + andre*0.05
    """
```

### 2.2 Schema
Lagre i eksisterende `fundamentals`-tabell:
- `series_id = "ANP_ETANOL_HIDR_CS_BRL_LITER"` (Centro-Sul vektet snitt)
- `series_id = "ANP_ETANOL_HIDR_SP_BRL_LITER"` (São Paulo isolert)
- `series_id = "ANP_GASOLINA_CS_BRL_LITER"` (for paritet vs sukker via etanol-blandingsforhold)

### 2.3 Driver
`src/bedrock/engine/drivers/agronomy.py::ethanol_parity_brl`

```python
@register("ethanol_parity_brl")
def ethanol_parity_brl(store, instrument, params):
    """Sugar/ethanol-paritet i cents/lb sukker-ekvivalent.

    paritet_cents_lb = (anhydrous_brl_per_liter / brl_usd_rate)
                     × (1 / 1.852 kg sugar / liter ethanol)
                     × 2.20462 lb/kg × 100

    Når paritet > sukker-pris → etanol mer attraktivt for møller →
    mindre sukker-mix → BULL #11.

    Returns 0..1 score: pris-paritet z-score over 60d.
    """
    etanol = store.get_fundamentals("ANP_ETANOL_HIDR_CS_BRL_LITER")
    brl = store.get_fundamentals("DEXBZUS")
    sb = store.get_prices("Sugar", tf="D1")["close"]

    # Konverter ANP hydrous til anhydrous-ekvivalent
    # (anhydrous er ~1.05x hydrous-pris i Brasil pga skatt-struktur)
    anhydrous = etanol * 1.05

    paritet = (anhydrous / brl) * (1 / 1.852) * 2.20462 * 100
    delta = paritet - sb
    z = (delta - delta.rolling(60).mean()) / delta.rolling(60).std()
    z_now = z.iloc[-1]

    # Map z-score til 0..1 score (z=+2σ = 1.0 = max bull)
    return _step(z_now, [(-2, 0.0), (-1, 0.25), (0, 0.5), (1, 0.75), (2, 0.9), (inf, 1.0)])
```

### 2.4 Sugar.yaml integrasjon
Erstatt `momentum_z` (CrudeOil proxy):

```yaml
cross:
  weight: 2
  drivers:
    - name: brl_chg5d
      weight: 0.50  # uendret
    - name: cot_ice_mm_pct
      weight: 0.20  # uendret
    - name: event_distance
      weight: 0.10  # uendret
    - name: ethanol_parity_brl
      weight: 0.20  # erstatter momentum_z(CrudeOil) — direkte måling
```

### 2.5 Cron-integrasjon
`config/fetch.yaml`:
```yaml
anp_ethanol:
  module: bedrock.fetch.anp_ethanol
  cron: "0 5 7 * *"        # 7. i mnd 05:00 Oslo (etter ANP ~5. publisering)
  stale_hours: 720          # månedlig
  on_failure: log_and_skip
  table: fundamentals
  ts_column: date
```

UI: `_FETCHER_HORIZONS["anp_ethanol"] = ["M"]` (månedlig kadens, kun macro).

## 3. Validerings-plan

### 3.1 Korrelasjon mot UNICA mix
Per analytiker-anbefaling:
```
ρ(ethanol_parity_brl_signal_t, unica.mix_sugar_pct_t+1) < -0.5
```
(høy paritet ⇒ neste UNICA-rapport viser lavere sukker-mix-andel)

Hvis |ρ| < 0.3 → driver-formel feil, må kalibreres.

### 3.2 Backtest A+ BUY 90d
Kjør backtest med vs uten driver. Forventet: Sharpe-løft ≥ 0.10 på A+ BUY 90d (cross-familie kommer fra 2.0 til 2.0 men driver-blanding endres).

## 4. Estimat

| Trinn | Tid |
|-------|-----|
| Fetcher (URL-discovery + CSV-parser + aggregering) | 2-3 t |
| Driver-implementasjon + tester | 2 t |
| YAML-integrasjon + systemd-units | 30 min |
| Backfill 14-års historikk fra ANP-arkiv | 1-2 t (2004 → 2026) |
| Validering (korrelasjon + backtest) | 1 t |
| **Total** | **~7 timer** |

## 5. Avhengigheter

- ANP-arkivet er stabilt (samme URL-mønster siden 2017+)
- Eldre data (2004-2016) i annet format — vurder hopp over historikk eller bygg separat parser
- Trenger DEXBZUS i fundamentals (allerede der)
- Trenger 1.852 kg/liter konverteringskonstant (industri-standard)

## 6. Når implementeres

Etter at backtest 5 (post-ENSO + seasonal-fix) viser om SELL-mean-reversion-fix er nok edge-løft, eller om vi trenger ekstra drivere som ANP-paritet for å nå målprestasjon.
