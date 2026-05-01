"""Generer markdown-rapport over driver-balanse og scoring-vekter.

Sub-fase 12.9 D5+ — bruker-bestilling for rebalanserings-analyse.
Produserer `docs/driver_balance_report_<YYYY-MM-DD>.md` med:

1. Driver registry-oversikt (alle 44 drivere, kategori, hvilke
   instrumenter som bruker dem)
2. Per-instrument family-vekt-matrise (per horisont)
3. Per-driver bruks-rapport (count, total weight-sum, horisont-spread)
4. Per-horisont effective driver count (etter Fase 3-filter)
5. Anomaly-flag (familie-sum ≠ 1.0; underrepresenterte drivere;
   over-konsentrert vekt)
6. Asset-class-distribusjon

Ikke-modifiserende: kun lese-operasjon. Output er md-fil med tabeller
operatør kan analysere offline.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from bedrock.config.instruments import load_all_instruments
from bedrock.engine import drivers as driver_registry

INSTRUMENTS_DIR = Path("config/instruments")
DEFAULTS_DIR = Path("config/defaults")
OUT_DIR = Path("docs")


def main() -> Path:
    configs = load_all_instruments(INSTRUMENTS_DIR, defaults_dir=DEFAULTS_DIR)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = OUT_DIR / f"driver_balance_report_{today}.md"

    lines: list[str] = []

    def w(s: str = "") -> None:
        lines.append(s)

    w(f"# Driver-balanse-rapport — {today}")
    w()
    w(f"**Generert:** {datetime.now(timezone.utc).isoformat()}")
    w(f"**Antall instrumenter:** {len(configs)}")
    w(f"**Antall registrerte drivere:** {len(driver_registry._REGISTRY)}")
    w()
    w("Bruk denne rapporten til å vurdere rebalansering av driver-vekter ")
    w("og horisont-filtrering. Hver seksjon er selvstendig — du kan ")
    w("hoppe direkte til den som er relevant for din analyse.")
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # Seksjon 1: Driver registry-oversikt
    # ──────────────────────────────────────────────────────────
    w("## 1. Driver-registry — registrert vs brukt")
    w()
    w("Alle drivere som er registrert via `@register_driver` i ")
    w("`src/bedrock/engine/drivers/`, sortert alfabetisk. Kolonnen ")
    w("**Brukt** viser hvor mange instrumenter har driveren wired ")
    w("inn i en YAML-familie. Drivere med 0 brukt-count er enten ")
    w("ny-introdusert eller dead-code-kandidat.")
    w()
    w("| Driver | Brukt på | Filer (instrumenter) |")
    w("|---|---:|---|")

    driver_to_instruments: dict[str, list[str]] = defaultdict(list)
    for inst_id, cfg in configs.items():
        seen = set()
        for fam in cfg.rules.families.values():
            for d in fam.drivers:
                if d.name not in seen:
                    driver_to_instruments[d.name].append(inst_id)
                    seen.add(d.name)

    all_registered = sorted(driver_registry._REGISTRY.keys())
    for name in all_registered:
        users = driver_to_instruments.get(name, [])
        users_str = ", ".join(sorted(users)) if users else "_(ubrukt)_"
        w(f"| `{name}` | {len(users)} | {users_str} |")
    w()
    unused = [n for n in all_registered if not driver_to_instruments.get(n)]
    if unused:
        w(f"⚠ **{len(unused)} drivere er registrert men ikke brukt** i noen YAML: ")
        w(f"`{', '.join(unused)}`")
        w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # Seksjon 2: Per-instrument family-vekt-matrise
    # ──────────────────────────────────────────────────────────
    w("## 2. Family-vekter per instrument × horisont")
    w()
    w("Family-weights fra `horizons:`-blokken i hver instrument-YAML. ")
    w("Disse styrer hvor mye HVER FAMILIE bidrar til total-score per ")
    w("horisont. Family-summen normaliseres ikke automatisk — operatør ")
    w("velger relativ vektlegging.")
    w()

    # Sorter per asset-class for lesbarhet
    by_class: dict[str, list[str]] = defaultdict(list)
    for inst_id, cfg in configs.items():
        # asset_class er på cfg.instrument
        ac = cfg.instrument.asset_class
        by_class[ac].append(inst_id)

    for ac in sorted(by_class.keys()):
        w(f"### {ac}")
        w()
        instruments = sorted(by_class[ac])
        all_families: set[str] = set()
        for inst_id in instruments:
            cfg = configs[inst_id]
            if hasattr(cfg.rules, "horizons"):
                for hspec in cfg.rules.horizons.values():
                    all_families.update(hspec.family_weights.keys())
            else:
                all_families.update(cfg.rules.families.keys())
        family_list = sorted(all_families)

        # Header
        header = "| Instrument | Horisont | " + " | ".join(family_list) + " | Sum | Max |"
        sep = "|---|---|" + "|".join(["---:"] * len(family_list)) + "|---:|---:|"
        w(header)
        w(sep)
        for inst_id in instruments:
            cfg = configs[inst_id]
            if hasattr(cfg.rules, "horizons"):
                for h_name, hspec in cfg.rules.horizons.items():
                    fw = hspec.family_weights
                    cells = [f"{fw.get(f, 0):.2f}" if fw.get(f) else "–" for f in family_list]
                    fw_sum = sum(fw.values())
                    w(
                        f"| {inst_id} | {h_name} | "
                        + " | ".join(cells)
                        + f" | {fw_sum:.2f} | {hspec.max_score:.1f} |"
                    )
            else:
                # Agri — ingen horisonter, vekter på family-spec direkte
                cells = []
                fw_sum = 0.0
                for f in family_list:
                    fam = cfg.rules.families.get(f)
                    if fam:
                        cells.append(f"{fam.weight:.2f}")
                        fw_sum += fam.weight
                    else:
                        cells.append("–")
                w(
                    f"| {inst_id} | (agri) | "
                    + " | ".join(cells)
                    + f" | {fw_sum:.2f} | {cfg.rules.max_score:.1f} |"
                )
        w()

    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # Seksjon 3: Per-driver bruksanalyse
    # ──────────────────────────────────────────────────────────
    w("## 3. Per-driver bruksanalyse")
    w()
    w("For hver brukte driver: hvilken familie den ligger i, gjennom- ")
    w("snittlig vekt over instrumentene som bruker den, vekt-spredning ")
    w("(min..max), horisont-filter (eller 'alle 3'), antall instrumenter.")
    w()
    w("**Sortert etter bruks-count.** Drivere med lav count + tung ")
    w("vekt er kandidater for å vurdere om de skal beholdes; drivere ")
    w("med høy count + uniform vekt er stabile fundamentale.")
    w()
    w(
        "| Driver | Familie | Antall inst | Vekt-snitt | Vekt-min..max | Horisonter | Total vekt-sum |"
    )
    w("|---|---|---:|---:|---|---|---:|")

    # Bygg per-driver aggregat
    driver_data: dict[str, dict] = defaultdict(
        lambda: {
            "weights": [],
            "families": set(),
            "horizons": set(),
            "instruments": set(),
            "horizon_filter_set": set(),  # for å se om de fleste er filtrert eller ikke
        }
    )
    for inst_id, cfg in configs.items():
        for fam_name, fam in cfg.rules.families.items():
            for d in fam.drivers:
                rec = driver_data[d.name]
                rec["weights"].append(d.weight)
                rec["families"].add(fam_name)
                rec["instruments"].add(inst_id)
                if d.horizons:
                    rec["horizon_filter_set"].add(tuple(sorted(d.horizons)))
                else:
                    rec["horizon_filter_set"].add(("alle",))

    sorted_drivers = sorted(driver_data.items(), key=lambda kv: -len(kv[1]["instruments"]))
    for name, rec in sorted_drivers:
        weights = rec["weights"]
        avg = sum(weights) / len(weights)
        wmin, wmax = min(weights), max(weights)
        families = ", ".join(sorted(rec["families"]))
        # Horisont-summary: hvis alle samme filter, vis det; ellers "varierer"
        if len(rec["horizon_filter_set"]) == 1:
            hf = next(iter(rec["horizon_filter_set"]))
            hor_str = "alle 3" if hf == ("alle",) else "+".join(hf)
        else:
            hor_str = "varierer"
        w(
            f"| `{name}` | {families} | {len(rec['instruments'])} | "
            f"{avg:.3f} | {wmin:.2f}..{wmax:.2f} | {hor_str} | "
            f"{sum(weights):.2f} |"
        )
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # Seksjon 4: Per-horisont effective driver count (etter Fase 3-filter)
    # ──────────────────────────────────────────────────────────
    w("## 4. Per-horisont effective driver count")
    w()
    w("Antall drivere som faktisk kjører på hver horisont per ")
    w("instrument, etter `DriverSpec.horizons`-filter (Fase 3). ")
    w("MAKRO som har færre drivere enn SCALP er typisk for instrumenter ")
    w("med tunge event_distance/aaii-drivere som er filtrert bort fra ")
    w("makro.")
    w()
    w("| Instrument | SCALP | SWING | MAKRO | Total drivere | Filtrerte |")
    w("|---|---:|---:|---:|---:|---:|")
    for inst_id in sorted(configs.keys()):
        cfg = configs[inst_id]
        total = 0
        filtered = 0
        per_h = {"SCALP": 0, "SWING": 0, "MAKRO": 0}
        for fam in cfg.rules.families.values():
            for d in fam.drivers:
                total += 1
                if d.horizons:
                    filtered += 1
                    for h in d.horizons:
                        per_h[h] += 1
                else:
                    for h in per_h:
                        per_h[h] += 1
        w(
            f"| {inst_id} | {per_h['SCALP']} | {per_h['SWING']} | "
            f"{per_h['MAKRO']} | {total} | {filtered} |"
        )
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # Seksjon 5: Anomaly-flagging
    # ──────────────────────────────────────────────────────────
    w("## 5. Anomalier — kandidat for rebalansering")
    w()
    w("Automatisk flagging av potensielle issue-r. Manuell vurdering ")
    w("kreves for hver — flagg betyr 'verdt å se på', ikke 'er bug'.")
    w()

    flags: list[tuple[str, str, str]] = []  # (severity, category, message)

    # 5a: Families der vekt-sum < 0.99 eller > 1.01 (ikke nær 1.0)
    for inst_id, cfg in configs.items():
        for fam_name, fam in cfg.rules.families.items():
            wsum = sum(d.weight for d in fam.drivers)
            if abs(wsum - 1.0) > 0.01:
                flags.append(
                    (
                        "WARN",
                        "family-sum-off",
                        f"{inst_id}.{fam_name}: driver-vekt-sum = {wsum:.3f} (forventet ≈ 1.0)",
                    )
                )

    # 5b: Drivere med vekt > 0.7 (over-konsentrert i én driver)
    for inst_id, cfg in configs.items():
        for fam_name, fam in cfg.rules.families.items():
            for d in fam.drivers:
                if d.weight > 0.70:
                    flags.append(
                        (
                            "INFO",
                            "high-weight",
                            f"{inst_id}.{fam_name}.{d.name}: vekt={d.weight:.2f} "
                            "(ev. fragilitet hvis driver feilberegnes)",
                        )
                    )

    # 5c: Drivere registrert men ikke brukt
    for name in unused:
        flags.append(("INFO", "unused", f"`{name}` registrert men ikke i noen YAML"))

    # 5d: Drivere brukt med veldig sprikende vekter (max/min > 5×)
    for name, rec in sorted_drivers:
        weights = rec["weights"]
        if len(weights) < 2:
            continue
        if min(weights) > 0 and max(weights) / min(weights) > 5.0:
            flags.append(
                (
                    "INFO",
                    "wide-weight-spread",
                    f"`{name}`: vekt {min(weights):.2f}..{max(weights):.2f} "
                    "across instruments (varierer 5×+; sjekk om bevisst)",
                )
            )

    # 5e: Drivere med inkonsistent horisont-filter (samme driver, ulik horisont per inst)
    for name, rec in sorted_drivers:
        if len(rec["horizon_filter_set"]) > 1:
            filters_str = " vs ".join(
                "+".join(f) if f != ("alle",) else "alle" for f in sorted(rec["horizon_filter_set"])
            )
            flags.append(
                (
                    "WARN",
                    "horizon-filter-mismatch",
                    f"`{name}`: ulik horizons-filter på instrumenter ({filters_str})",
                )
            )

    if flags:
        flags.sort(key=lambda x: (x[0] != "WARN", x[1], x[2]))
        for severity, category, msg in flags:
            w(f"- **[{severity}] [{category}]** {msg}")
    else:
        w("_Ingen anomalier flagget._")
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # Seksjon 6: Asset-class-distribusjon
    # ──────────────────────────────────────────────────────────
    w("## 6. Asset-class-distribusjon")
    w()
    w("| Asset class | Instrumenter | Snitt drivere/inst |")
    w("|---|---|---:|")
    for ac in sorted(by_class.keys()):
        ids = sorted(by_class[ac])
        avg_drivers = sum(
            sum(len(fam.drivers) for fam in configs[i].rules.families.values()) for i in ids
        ) / len(ids)
        w(f"| {ac} | {', '.join(ids)} | {avg_drivers:.1f} |")
    w()

    # ──────────────────────────────────────────────────────────
    # Footer
    # ──────────────────────────────────────────────────────────
    w("---")
    w()
    w(f"_Generert av_ `scripts/analysis/driver_balance_report.py` _på {today}._")
    w()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rapport skrevet til: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
