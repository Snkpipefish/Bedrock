# Hvordan skrive en ny driver (Python)

Skeleton — utvides i Fase 1.

## Kontrakt

Alle drivere har nøyaktig denne signaturen:

```python
from bedrock.engine.drivers import register
from bedrock.data.store import DataStore

@register("<driver_navn>")
def <driver_navn>(store: DataStore, instrument: str, params: dict) -> float:
    """
    Beskriv hva driveren måler, hva 0 og 1 betyr, og hvilke data den leser.
    """
    ...
    return <float 0-1 eller -1 til 1>
```

## Regler

1. **Returner 0-1** for unidirectional drivere, **-1 til 1** for bi-direksjonale.
2. **Deterministisk.** Samme input → samme output. Ingen tilfeldighet, ingen
   tid-avhengighet utover det som er i `data`.
3. **Ingen side-effekter.** Ikke skriv filer, ikke POST noe sted, ikke oppdater
   state. Kun les fra `store` og returner float.
4. **Feil returnerer 0.0 og logger.** Ikke kast exception — det stopper scoring
   for hele instrumentet.
5. **Params-validering:** sjekk at required params er til stede. Hvis ikke, log
   + return 0.
6. **Ikke gjem forretnings-logikk i params.** Hvis en driver har helt ulik
   oppførsel basert på en param, lag to drivere.

## Eksempel (skal implementeres i Fase 1)

```python
@register("sma200_align")
def sma200_align(store: DataStore, instrument: str, params: dict) -> float:
    """
    Returnerer 0-1 basert på om prisen er over SMA200 på gitt TF.
    0 = godt under, 0.4 = like under, 0.6 = like over, 1 = godt over.
    Params:
      tf: timeframe-streng ("D1", "4H", "1H"). Default "D1".
    """
    tf = params.get("tf", "D1")
    prices = store.get_prices(instrument, tf=tf, lookback=250)
    if len(prices) < 200:
        return 0.0  # ikke nok data
    sma = prices.rolling(200).mean().iloc[-1]
    close = prices.iloc[-1]
    if close > sma * 1.01: return 1.0
    if close > sma:        return 0.6
    if close > sma * 0.99: return 0.4
    return 0.0
```

## Tester for nye drivere

Hver driver skal ha minst 3 logiske tester i `tests/logical/test_drivers_<familie>.py`:

1. Boundary-case lav (forvent ~0)
2. Boundary-case høy (forvent ~1)
3. Intermediate (forvent verdi i mellom)

Pluss en unit-test som verifiserer at driveren er registrert i registry.

## Navnekonvensjon

- Snake_case
- Starter ofte med hva som måles: `sma200_align`, `cot_mm_percentile`, `real_yield_change`
- Slutter med hva det uttrykker: `_align`, `_pct`, `_change`, `_bias`, `_regime`
- Undgå forkortelser som ikke er standard i markedet

## Hvordan legge til driver i eksisterende regel

1. Skriv driver-funksjonen (`src/bedrock/engine/drivers/<familie>.py`)
2. Skriv tester (`tests/logical/test_drivers_<familie>.py`)
3. Legg til i relevant YAML:
   ```yaml
   # config/instruments/gold.yaml
   families:
     trend:
       drivers:
         - {name: sma200_align, weight: 0.4, params: {tf: D1}}
         - {name: din_nye_driver, weight: 0.2, params: {...}}  # ← ny linje
   ```
4. Kjør `uv run pytest`
5. Kjør `uv run bedrock dry-run --rules gold` for å se impact
6. Commit med `feat(drivers): add <navn> + update gold yaml`
