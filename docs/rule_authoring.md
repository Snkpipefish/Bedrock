# Hvordan skrive en ny regel (YAML)

Dette dokumentet utvides i Fase 1 når den første Engine-implementasjonen er på
plass. Foreløpig en skeleton som beskriver forventet form.

## Prinsipp

**YAML sier *hva* og *hvor mye*. Python sier *hvordan*.**

Ingen uttrykk, ingen betingelser, ingen `eval` i YAML. Hvis du trenger logikk,
legg det i en driver-funksjon.

## Struktur per instrument

Se `PLAN.md` § 4.2 og 4.3 for konkrete eksempler (Gold financial, Corn agri).

Minimum-felter:

```yaml
inherits: family_financial | family_agri
instrument:
  id: <string>
  asset_class: fx | metals | energy | indices | crypto | grains | softs
  ticker: <string>
  cfd_ticker: <string>     # navn hos broker
aggregation: weighted_horizon | additive_sum
families:
  <family_name>:
    drivers:
      - {name: <driver-navn>, weight: <float>, params: {...}}
grade_thresholds:
  A_plus: {...}
  A: {...}
  B: {...}
```

## Arv

Defaults-filer i `config/defaults/` gir felles verdier. Instrument-fil overstyrer
kun det den trenger.

## Validering

Alle YAML-filer valideres med Pydantic v2-schema ved lasting. Feil gir hard exit
med linje-nummer — ingen lydløs fallback.

## Dry-run før commit

Før en regel-endring pushes til main skal du kjøre:

```bash
uv run bedrock dry-run --rules config/instruments/gold.yaml --since 7d
```

Outputen viser hvilke signaler som endrer seg i forhold til forrige regelversjon
på siste uke med data. Hvis du er OK med diffen, commit. Hvis du ikke skjønner
hvorfor noe endret seg, bruk `bedrock explain` for å grave.

(Disse CLI-kommandoene eksisterer ikke ennå — de kommer i Fase 1-2.)
