# ADR-003: Gates via named-function registry, ikke string-DSL

**Status:** Accepted
**Dato:** 2026-04-24 (Fase 5 session 25)

## Kontekst

PLAN § 4.2 foreslo gate-syntaks med uttrykk som streng:

```yaml
gates:
  - {when: "event_distance < 3h", cap_grade: A}
  - {when: "data_quality = stale", cap_grade: B}
```

En string-DSL krever en parser/evaluator. Tre kandidater:

1. **`eval()` / `exec()`** — usikkert, eksponerer hele Python. Uaktuelt.
2. **Restriktert AST-walker** (filtrerer `ast.parse`-nodene) — komplisert
   å gjøre riktig, vanskelig å audite, risiko for bypass.
3. **Custom parser** for et mini-språk — substansiell implementering,
   vanlig kilde til bugs og sikkerhetshull.

Alle tre gir oss også problem med navngivning av felter: "event_distance"
må mappe til en datakilde (kalender-fetcher), "data_quality" til en
annen (freshness-sjekker).

Samtidig har vi allerede et velfungerende mønster i kodebasen: **driver-
registry** (`@register("sma200_align")`). Samme mønster kan gjenbrukes
for gates.

## Beslutning

Gates uttrykkes som **navn + parametre**, ikke som uttrykk:

```yaml
gates:
  - {name: event_distance_lt, params: {hours: 3}, cap_grade: A}
  - {name: data_quality_stale, cap_grade: B}
```

`@gate_register("navn")` dekorerer Python-funksjoner:

```python
@gate_register("event_distance_lt")
def event_distance_lt(context: GateContext, params: dict) -> bool:
    hours = params["hours"]
    return context.hours_to_next_event < hours
```

Gate-funksjonen returnerer `True` hvis gaten skal utløses (kapping
anvendes), `False` ellers. Engine samler opp utløste gater og anvender
lavest `cap_grade` på computed grade.

## Konsekvenser

### Positive

- **Konsistent med drivers**: samme mønster (`@register` + signatur +
  registry-lookup) reduserer kognitiv load for nye bidragsytere.
- **Sikker**: ingen runtime eval av brukerinput; gate-logikk er alltid
  revisjonerbar Python-kode i `bedrock.engine.gates.*`.
- **Testbar**: gate-funksjoner er rene funksjoner, enkle å unit-teste.
- **Typet**: `params`-dict valideres av gate-funksjonen selv
  (KeyError ved manglende felt fanges med tydelig feil).

### Negative

- **Flere Python-linjer for nye gates**: kan ikke skrive ny gate-logikk
  kun i YAML. Motvirkes ved å ha en liten standard-bibliotek av
  parametriserbare gates (`score_below`, `min_active_families`,
  `event_distance_lt`, `data_quality_stale`).
- **PLAN § 4.2-syntaks må endres**: når PLAN oppdateres, bytt
  `when: "..."` til `name:`/`params:`/`cap_grade:`.

### Ikke-valgt

- **Generisk DSL** kan senere introduseres som et bredere uttrykk-
  språk på toppen av registry-funksjonene (f.eks. OR-kombinasjon av
  flere gates). Først når konkret behov viser seg. ADR må da oppdateres.

## Felles gate-funksjons-kontrakt

```python
def gate(context: GateContext, params: dict[str, Any]) -> bool: ...
```

- **Returnerer** `True` = utløst (anvend cap), `False` = ikke utløst.
- **Ingen bivirkninger**: gate-funksjoner leser kontekst + params, ingen
  I/O, ingen global state.
- **Deterministisk**: samme input gir samme resultat (nødvendig for
  explain-trace).
- **Feil-håndtering**: manglende params → la Python kaste KeyError;
  Engine logger med gate-navn og instrument for debugging.

## Referanser

- PLAN § 4.2 (Gold-YAML)
- `docs/decisions/001-one-engine-two-aggregators.md` (driver-registry-
  mønster)
- `src/bedrock/engine/drivers/__init__.py` (implementasjon av
  driver-registry, brukes som mal)
