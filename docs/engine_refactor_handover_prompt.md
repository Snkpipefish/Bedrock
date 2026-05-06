# Handover-prompt for nytt kontekst-vindu — Engine refactor sub-fase 12.12 Fase A

Kopier alt under `---` og lim inn som første melding i nytt vindu.

---

Vi har identifisert 10 fundamentale design-issues i Bedrock engine. Sub-fase 12.12 åpner med Fase A (coordination layer). **Les disse 4 filene først, i denne rekkefølgen:**

1. `docs/engine_fundamental_review_2026-05-06.md` — full issue-katalog (10 problemer)
2. `docs/engine_refactor_plan_2026-05.md` — 3-fase plan med detaljerte sub-tasks
3. `STATE.md` linje ~100 — sub-fase 12.11+ LUKKET (siste kontekst)
4. `config/instruments/sugar.yaml` — kompleksitets-eksempel (5-driver unica-familie)

## Status ved oppstart

- Sub-fase 12.11+ LUKKET 2026-05-06 (alle 13 analytiker-tiltak ferdig + UN Comtrade real-time India eksport).
- Sukker engine produserer kontradiktoriske signaler: MAKRO BUY 8.28 (A) + MAKRO SELL 9.72 (A) begge over publish-floor.
- Audit på alle 22 instrumenter avslørte:
  - **16 instrument-horisont-konflikter** (BUY+SELL begge over floor)
  - **11 instrumenter publiserer samme retning på flere horisonter** med duplikat-entry
- Pipeline-helse grønn. CI grønn (ba7b4a1 + cb93c4d ryddet ruff/openpyxl).

## Hva Fase A skal levere (1-2 dager arbeid)

4 sub-tasks som adresserer Issue 1, 2, 7, 8:

### A1: Cross-direction net-bias filter (~3 timer)
- Ny step i `src/bedrock/orchestrator/signals.py` etter `_compute_scores`
- Hvis `|sell_score - buy_score| < threshold` (default 1.5): blokker BEGGE retninger
- Hvis Δ ≥ threshold: kun dominant retning publiseres
- Konfig: `config/defaults/orchestrator.yaml::net_bias_filter` med per-asset_class threshold-overrides
- Tester: `tests/unit/test_orchestrator_net_bias.py`
- **Akseptanse:** etter A1, audit viser 0 instrumenter med begge retninger publisert

### A2: Cross-horizon dedup på setup-nivå (~3 timer)
- Ny step etter `build_setup` i orchestrator
- Hvis samme (instrument, direction) har flere horisonter med entry-spread < 0.3%: behold KUN lengste horisont
- De andre markeres skip_reason='subsumed_by_longer_horizon'
- Tester: `tests/unit/test_orchestrator_horizon_dedup.py`
- **Akseptanse:** maks 1 setup per (instrument, direction) når entries er innenfor 0.3% spread

### A3: Bot per-instrument risk-cap (~2 timer)
- Modifiser `src/bedrock/bot/risk.py::calculate_position_size`
- Ny `open_positions`-param + `per_instrument_max_pct: 1.0` i bot.yaml
- Hvis flere setups på samme instrument: del 1% risk-cap
- Tester: `tests/unit/test_bot_risk_per_instrument.py`
- **Akseptanse:** sum(risk_pct per instrument) ≤ 1.0 til enhver tid

### A4: Horisont-aware entry-distance (~2 timer)
- Modifiser `src/bedrock/setups/generator.py::build_setup`
- Krev minst (0.3, 0.7, 1.5)×ATR avstand for (SCALP, SWING, MAKRO) entry vs current pris
- Tester: `tests/unit/test_setup_horizon_distance.py`
- **Akseptanse:** MAKRO-setups har entry > 1.5×ATR fra current; varierer fra SCALP/SWING når struktur tillater

## Validerings-flyt etter alle 4

```bash
# 1. Pyright + tests
PYTHONPATH=src .venv/bin/python -m pytest tests/ -x -q

# 2. Re-kjør signals-all
.venv/bin/bedrock signals-all
.venv/bin/bedrock signals-all --bot-only --output data/signals_bot.json

# 3. Audit konflikter
PYTHONPATH=src .venv/bin/python -c "
import json
from collections import defaultdict
d = json.load(open('data/signals.json')) + json.load(open('data/agri_signals.json'))
by_inst = defaultdict(list)
for e in d:
    if e.get('published'):
        by_inst[(e['instrument'], e['horizon'])].append(e)
conflicts = [(k, v) for k, v in by_inst.items() if len({e['direction'] for e in v}) > 1]
print(f'Dual-direction-conflicts efter A1: {len(conflicts)} (forventet 0)')
"

# 4. Snapshot-diff
PYTHONPATH=src .venv/bin/python scripts/snapshot/score_baseline.py \
    --diff-against tests/snapshot/expected/score_baseline.json | head -30
```

## Worktree

Du jobber **direkte på main** (ikke worktree — bruker har sagt at hen ikke pleier å bruke worktrees). Auto-push hook pusher hver commit til origin/main automatisk.

## Commit-strategi

- Ett commit per sub-task (A1, A2, A3, A4)
- Tag etter hver: `git tag v0.12.12-fase-a1` osv
- STATE.md-update separat etter alle 4

## Begrensninger / ikke gjør

- Ikke restart engine fra scratch — beholder driver-bibliotek
- Ikke endre driver-logikk i Fase A (kun coordination + risk-aggregering)
- Ikke endre score-aggregeringsformel (additive_sum bevares)
- Ikke endre familie-vekter (det er Fase C)
- Ikke wire nye datakilder (det er Fase B)

## Når Fase A er ferdig

Kommenter til operatør:
```
Fase A LUKKET. Konflikter redusert fra 16 → N. Multi-horizon-publish redusert fra 11 → M.
Snapshot-baseline regenerert (X% færre publiserte signaler totalt).
Klart for Fase B (forward-data-feeds) eller Fase C (vekt-ML) — operatør velger neste.
```

Spør operatør om Fase B eller C neste. Anbefaling: Fase B (1 uke, leverer ny analytisk kapasitet) før Fase C (2-3 uker, mer kompleks).

## Referansedata

- 22 instrumenter i `config/instruments/`
- 7 familier × 19 drivere (sukker som referanse-eksempel)
- 99 registrerte drivere totalt (bedrock.engine.drivers.all_names())
- ~2918 tester (alle grønne)
- Test-cmd: `PYTHONPATH=src .venv/bin/python -m pytest tests/`
- Lint: `uv run ruff check .` + `uv run ruff format --check .`

## Pipeline-helse-blikk ved oppstart

```bash
bash scripts/session_health.sh
```

Hvis rød: ikke start Fase A før helse er grønn — ikke bygg ny kode på trasig datagrunnlag.
