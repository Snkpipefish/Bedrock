# ADR-004: Python 3.10 som minimum-versjon (ikke 3.12)

Dato: 2026-04-25
Status: accepted
Fase: 9 (oppdaget mid-runde-1, lukker session 50)

## Kontekst

Pyproject opprinnelig satt `requires-python = ">=3.12"` med begrunnelsen
"siste Python — best mulig". Denne beslutningen var udokumentert og ikke
tatt eksplisitt; den ble bare lagt inn ved scaffold.

To problemer ble oppdaget i Fase 9:

1. **Lokal utvikler-maskin mangler Python 3.12.** Ubuntu 22.04 LTS har
   Python 3.10 som default; 3.12 må installeres manuelt via `pyenv`,
   `deadsnakes` PPA eller bygges fra kilde. Bruker har ikke gjort
   dette og har ikke planlagt å gjøre det.

2. **CI vs lokal divergens.** CI installerte Python 3.12 via
   `astral-sh/setup-uv@v3` mens lokalt testes på 3.10. Når ruff
   auto-fix endret `datetime.timezone.utc` → `datetime.UTC`
   (UP017-regel, 3.11+ syntaks), brøt det all lokal pytest-kjøring
   selv om CI gikk grønt.

ADR-002 dokumenterer SSE4.2/AVX-mangelen på produksjons-hardwaren —
men det dreier seg om binære **wheels**, ikke om Python-interpreter-
versjon. Selv produksjon kjører på Python 3.10 fra Ubuntu repos. Det
er ingen kjent grunn til at Bedrock trenger 3.11+-features.

## Beslutning

`requires-python = ">=3.10"`. Alle koderegler målrettes mot 3.10:

- `pyproject.toml`: `[project] requires-python = ">=3.10"`
- `pyproject.toml`: `[tool.ruff] target-version = "py310"`
- `pyproject.toml`: `[tool.pyright] pythonVersion = "3.10"`
- `pyproject.toml`: `[tool.ruff.lint] ignore` inkluderer `UP017`
  (datetime.UTC er 3.11+; vi bruker `timezone.utc`)
- `.github/workflows/ci.yml`: `uv python install 3.10`

## Praktiske implikasjoner

**Tillatt syntaks (3.10):**
- `X | Y` union (PEP 604) — OK fra 3.10
- `match`-statements
- Parenthesized context managers
- `dict[K, V]`, `list[T]` (PEP 585)

**Ikke tillatt (3.11+):**
- `datetime.UTC` — bruk `datetime.timezone.utc`
- `Self`-type i typing — bruk `typing_extensions.Self` hvis nødvendig
- Exception groups (`except*`)
- `tomllib` i stdlib — bruk `tomli` (selv om det er ubrukt nå)
- `ReadableBuffer`/`WriteableBuffer` direkte i typing

**Tillatt med PEP 695-syntaks (3.12+):**
- `type Alias = ...` — bruk `Alias: TypeAlias = ...` istedenfor
- `class C[T]:` — bruk `class C(Generic[T]):` istedenfor

Ruff's `UP040` (PEP 695 type alias) er allerede ignorert i pyproject.

## Begrunnelse for å ikke kreve 3.11/3.12

- **Ubuntu 22.04 LTS** (default på laptop, 2024-2027 support-vindu)
  leverer 3.10. Å kreve nyere skaper friksjon for utvikleren uten
  kjent gevinst.
- **Ingen library-krav** Bedrock bruker krever 3.11+: pydantic ≥2.9,
  pandas ≥2.2, numpy 2.2.x, flask 3.0, twisted 24.3 — alle støtter 3.10.
- **CI-vs-lokal-paritet** er viktigere enn å ha siste Python.
  Divergensen er en silent footgun (kode passerer CI, feiler lokalt).

Hvis 3.12-spesifikke features skulle bli ønskelig senere (f.eks.
`Self`-type, type-statement, PEP 695), evaluer da om det rettferdiggjør
å bumpe minimum og samtidig oppgradere Ubuntu LTS-baseline.

## Referanser

- PEP 604 (X | Y unions): 3.10
- PEP 585 (built-in generics): 3.9
- PEP 695 (type-statement): 3.12
- ADR-002: SSE4.2/AVX-constraint på produksjons-hardware (separat sak)
