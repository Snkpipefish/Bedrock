"""Score-snapshot-baseline for sub-fase 12.7 R1+R3+R4.

Genererer (instrument, horizon, direction) -> {score, grade,
family_scores} for alle 22 instrumenter. Brukes som regresjons-anker
for å verifisere at horisont-refactoren (ADR-010) er bit-identisk
mot dagens scoring.

Bruk:

    PYTHONPATH=src .venv/bin/python scripts/snapshot/score_baseline.py
        [--db data/bedrock.db]
        [--out tests/snapshot/expected/score_baseline.json]
        [--diff-against tests/snapshot/expected/score_baseline.json]

- Uten ``--diff-against``: skriver ny JSON til ``--out``.
- Med ``--diff-against``: leser eksisterende JSON, regenererer scores,
  differ feltene, skriver ut alle forskjeller. Exit-kode 0 hvis null
  forskjeller, 1 hvis det er noen.

Forventet kjøre-tid: 30-90 sekunder for alle 104 score-kall (15
financial × 3 horisonter × 2 retninger + 7 agri × 1 × 2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Sørg for at vi finner `bedrock` ved direkte invocation.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bedrock.config.instruments import load_instrument_config  # noqa: E402
from bedrock.data.store import DataStore  # noqa: E402
from bedrock.engine.engine import AgriRules, FinancialRules  # noqa: E402
from bedrock.orchestrator.score import score_instrument  # noqa: E402
from bedrock.setups.generator import Direction  # noqa: E402

INSTRUMENTS_DIR = _REPO_ROOT / "config" / "instruments"
DEFAULT_DB = _REPO_ROOT / "data" / "bedrock.db"
DEFAULT_OUT = _REPO_ROOT / "tests" / "snapshot" / "expected" / "score_baseline.json"

# Antall desimaler for score/family_score. 9 holder bit-identitet for
# floats som passer i double (15-17 sig-figs); JSON serialiserer floats
# som strenger, så vi unngår plattform-formatting-drift.
_FLOAT_PRECISION = 12


def _round(x: float) -> float:
    """Rund til _FLOAT_PRECISION desimaler — sikrer cross-platform-
    deterministisk JSON-output."""
    return round(float(x), _FLOAT_PRECISION)


def _build_combos() -> list[tuple[str, str | None]]:
    """Returner (instrument_id, horizon)-par for alle YAMLs.

    For financial: tre rader per instrument (SCALP/SWING/MAKRO).
    For agri: én rad per instrument med horizon=None.
    """
    combos: list[tuple[str, str | None]] = []
    for yaml_path in sorted(INSTRUMENTS_DIR.glob("*.yaml")):
        cfg = load_instrument_config(yaml_path)
        inst_id = cfg.instrument.id
        if isinstance(cfg.rules, FinancialRules):
            for h in sorted(cfg.rules.horizons.keys()):
                combos.append((inst_id, h))
        elif isinstance(cfg.rules, AgriRules):
            combos.append((inst_id, None))
    return combos


def _key(instrument: str, horizon: str | None, direction: str) -> str:
    """Key-format brukt i JSON-outputen."""
    h = horizon if horizon is not None else "NONE"
    return f"{instrument}|{h}|{direction}"


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Plukk ut feltene som inngår i score-uendret-garantien.

    Vi bevarer score, grade, max_score, active_families, gates_triggered,
    og per-family score (uten driver-trace — det blir for stort, og
    family-score er den naturlige sjekkpunktet for aggregering)."""
    return {
        "score": _round(result.score),
        "grade": result.grade,
        "max_score": _round(result.max_score),
        "active_families": result.active_families,
        "gates_triggered": list(result.gates_triggered),
        "family_scores": {name: _round(fam.score) for name, fam in result.families.items()},
    }


def _generate(db_path: Path) -> dict[str, dict[str, Any]]:
    """Generer score for alle (instrument, horizon, direction)-kombinasjoner."""
    store = DataStore(db_path)
    out: dict[str, dict[str, Any]] = {}
    combos = _build_combos()
    print(f"Scoring {len(combos)} (instrument, horizon)-kombinasjoner × 2 retninger ...")
    for instrument, horizon in combos:
        for direction in (Direction.BUY, Direction.SELL):
            try:
                result = score_instrument(
                    instrument,
                    store,
                    horizon=horizon,
                    direction=direction,
                )
            except Exception as exc:
                # Vi vil ikke at score-feil skal skjule snapshot-baseline.
                # Logg + fortsett — manglende rad i baseline = feil i scoring.
                print(
                    f"  WARN {instrument} h={horizon} dir={direction.value}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                continue
            key = _key(instrument, horizon, direction.value)
            out[key] = _result_to_dict(result)
    return out


def _diff(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Returner liste med forskjeller. Tom liste = ingen forskjeller."""
    diffs: list[str] = []
    only_in_expected = expected.keys() - actual.keys()
    only_in_actual = actual.keys() - expected.keys()
    for k in sorted(only_in_expected):
        diffs.append(f"MISSING from actual: {k}")
    for k in sorted(only_in_actual):
        diffs.append(f"EXTRA in actual: {k}")
    for k in sorted(expected.keys() & actual.keys()):
        e, a = expected[k], actual[k]
        if e != a:
            diffs.append(
                f"CHANGED {k}:\n  expected: {json.dumps(e, sort_keys=True)}\n  actual:   {json.dumps(a, sort_keys=True)}"
            )
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--diff-against",
        type=Path,
        default=None,
        help="Hvis satt, regenerer scores og diff mot eksisterende baseline-JSON. Skriver ikke noen fil.",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"DB ikke funnet: {args.db}", file=sys.stderr)
        return 2

    actual = _generate(args.db)

    if args.diff_against is not None:
        if not args.diff_against.exists():
            print(f"--diff-against fil ikke funnet: {args.diff_against}", file=sys.stderr)
            return 2
        expected = json.loads(args.diff_against.read_text())
        diffs = _diff(expected, actual)
        if not diffs:
            print(f"OK — 0 forskjeller mot {args.diff_against} ({len(actual)} rader sammenlignet)")
            return 0
        print(f"FAIL — {len(diffs)} forskjeller mot {args.diff_against}:", file=sys.stderr)
        for d in diffs:
            print(f"  {d}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    print(f"Skrev {len(actual)} rader til {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
