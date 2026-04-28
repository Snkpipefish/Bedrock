# Snapshot-tester

Regresjons-anker for sub-fase 12.7 horisont-refactor (Spor R, ADR-010).

## Hva snapshotene fanger

`expected/score_baseline.json`: fryst (instrument, horizon, direction) →
{score, grade, max_score, active_families, gates_triggered,
family_scores}-mapping for alle 22 instrumenter × relevante horisonter
× 2 retninger (104 rader: 15 financial × 3 × 2 + 7 agri × 1 × 2).

## Hvordan generere / verifisere

Regenerer baseline mot gjeldende DB-tilstand:

    PYTHONPATH=src .venv/bin/python scripts/snapshot/score_baseline.py

Diff gjeldende scoring mot baseline (exit 0 = ingen forskjeller):

    PYTHONPATH=src .venv/bin/python scripts/snapshot/score_baseline.py \
        --diff-against tests/snapshot/expected/score_baseline.json

## Kritisk for R3/R4

Baseline-en er kun gyldig mot **samme DB-tilstand** som da den ble
generert. SQLite-filen `data/bedrock.db` oppdateres av:

- Systemd fetch-timere (prices, COT, FRED, etc.)
- Manuelle backfill-skripts
- Pytest-tester som leser/skriver mot live DB (ikke isolert fixture)

Dette betyr at en baseline tatt i dag og diff'et om en uke vil vise
DRIFT som er data-relatert, ikke kode-relatert. For å bruke
snapshoten som regresjons-anker for en refactor:

1. **Generer baseline rett før refactor-arbeidet starter**, med stoppet
   fetch-aktivitet hvis mulig. Commit baselinen.
2. **Diff i samme session**, så snart koden er endret, mens DB-tilstanden
   fortsatt matcher baselinen.
3. **Hvis diff er ikke-null:** undersøk om det er kode-drift (kritisk —
   må forklares) eller data-drift (regenerer baseline mot ny DB-state).
4. **R3/R4 commits:** hver driver-refactor og hver familie-batch i R4
   må ha 0-diff-bekreftelse i commit-meldingen, evt. eksplisitt notert
   som "ny driver lagt til" eller "familie-sammensetning endret".

## R1-snapshot (ADR-010 verifikasjon)

R1 verifiserte engine-patchen som bit-identisk via PRE/POST-patch-diff
i samme session (commit `feat(engine): horisont-propagering`):

- PRE-patch baseline tatt 2026-04-28 12:27 (104 rader).
- POST-patch diff samme dag 12:36: **0 forskjeller på 104 rader**.
- Baseline regenerert mot oppdatert DB-state etter at full pytest-suite
  hadde modifisert `data/bedrock.db` — samme 104 rader, men score-
  verdier reflekterer nå current DB. Bevaringa av engine-bit-identitet
  er fortsatt verifisert; den nye baselinen er det fremtidige anker.

## Når oppdatere expected/

- **Eksplisitt nytt baseline-anker** før en refactor starter: kjør
  `score_baseline.py` (uten `--diff-against`) → JSON skrevet → commit
  som "test(snapshot): refresh baseline before <refactor>".
- **Aldri** "fix" en uventet diff ved å overskrive baselinen uten å
  forstå hvorfor diff-en oppstod. Hvis koden er endret, må diff-en
  være forklart i commit-meldingen.
