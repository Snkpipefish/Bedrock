"""Generer data-utnyttelses-rapport for rebalanserings-analyse.

Komplementær til `driver_balance_report.py`. Mens den fokuserer på
hvilke drivere brukes med hvilke vekter, kartlegger denne hvilken
DATA som faktisk leses og hvor mye av historikken vi bruker.

Output: `docs/data_utilization_report_<date>.md` med 6 seksjoner:

1. SQLite-tabeller — total + brukt + ubrukt
2. Per-driver data-kilder (tabeller + tids-vindu)
3. Historikk-utnyttelse (har vs bruker)
4. Eksterne API-kilder vi har keys/tilgang til
5. Arkitektur-sjekk: hvor enkelt er det å legge til/fjerne drivere
6. Anbefalte data-utvidelser (potensielle drivere)

Lese-only. Operatør analyserer offline.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

DB_PATH = Path("data/bedrock.db")
OUT_DIR = Path("docs")
DRIVERS_DIR = Path("src/bedrock/engine/drivers")
INSTRUMENTS_DIR = Path("config/instruments")
DEFAULTS_DIR = Path("config/defaults")
FETCH_YAML = Path("config/fetch.yaml")
SECRETS_FILE = Path.home() / ".bedrock" / "secrets.env"


def get_table_stats() -> list[dict]:
    """Hent alle tabeller med row count + date-range hvis mulig."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
    stats = []
    for t in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            row_count = cur.fetchone()[0]
        except sqlite3.Error:
            row_count = 0

        # Identifiser tids-kolonne (date, ts, observation_ts, etc.)
        cur.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cur.fetchall()]
        time_col = None
        for cand in (
            "date",
            "ts",
            "observation_ts",
            "report_date",
            "event_ts",
            "gas_day_start",
            "month",
            "week_ending",
            "calendar_year",
        ):
            if cand in cols:
                time_col = cand
                break

        date_min = date_max = None
        if time_col and row_count:
            try:
                cur.execute(f"SELECT MIN({time_col}), MAX({time_col}) FROM {t}")
                date_min, date_max = cur.fetchone()
            except sqlite3.Error:
                pass

        stats.append(
            {
                "table": t,
                "rows": row_count,
                "time_col": time_col,
                "date_min": date_min,
                "date_max": date_max,
                "columns": cols,
            }
        )
    conn.close()
    return stats


def find_table_references_in_drivers() -> dict[str, set[str]]:
    """Skann driver-fil-er for hvilke `store.get_*` / `TABLE_*` referanser brukes."""
    refs: dict[str, set[str]] = defaultdict(set)
    if not DRIVERS_DIR.exists():
        return {}
    for f in sorted(DRIVERS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        text = f.read_text()
        # Find @register decorators + their target functions
        # Naive: find all "register(...)" + then for each look at the file globally
        registered = re.findall(r'@register\("([^"]+)"\)', text)
        # Find table-relevant references. We'll look at each function's body.
        # Simpler: associate ALL store.get_* in file with all registered drivers
        gets = re.findall(r"store\.get_(\w+)", text)
        for drv in registered:
            for g in gets:
                refs[drv].add(g)
    return dict(refs)


def get_lookback_params() -> dict[str, list[tuple[str, int]]]:
    """For hver driver-funksjon, finn `lookback_*`-parameter-default.

    Heuristisk: scan driver-fil-er for `params.get("lookback_X", N)`-mønster.
    """
    out: dict[str, list[tuple[str, int]]] = defaultdict(list)
    pattern = re.compile(r'params\.get\("(lookback_\w+|window\w*)"\s*,\s*(\d+)')
    for f in sorted(DRIVERS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        text = f.read_text()
        # Find @register block + extract lookback in same function
        # Simpler aggregate per file
        registered = re.findall(r'@register\("([^"]+)"\)', text)
        matches = pattern.findall(text)
        for drv in registered:
            for param_name, default in matches:
                out[drv].append((param_name, int(default)))
    return out


def list_external_apis() -> list[dict]:
    """Liste eksterne kilder + om vi har key satt + hva vi henter."""
    sources = [
        {
            "name": "FRED (Federal Reserve)",
            "env": "FRED_API_KEY",
            "url": "https://fred.stlouisfed.org/docs/api/fred/",
            "current_use": "DGS10, T10YIE, DTWEXBGS, VIXCLS, NFCI, WALCL, WTREGEN, DGS2, foreign 10Y, AAA10Y, BAA10Y, RRPONTSYD",
            "available_more": (
                "800,000+ økonomiske serier — manglende: M2, "
                "industrial production, ISM PMI, employment data, "
                "housing starts, retail sales, CPI sub-components, "
                "yield-spread (3M-10Y), TED spread, real GDP, "
                "consumer confidence (UMCSENT), federal funds futures (DFEDTAR)"
            ),
        },
        {
            "name": "USDA NASS QuickStats",
            "env": "BEDROCK_NASS_API_KEY",
            "url": "https://quickstats.nass.usda.gov/api",
            "current_use": "Crop Progress (PLANTED/SILKING/HARVESTED/GOOD_EXCELLENT) for CORN/SOYBEAN/WHEAT/COTTON",
            "available_more": (
                "Yields, production estimates, prices received, stocks "
                "(grain in storage), exports, imports, planted vs harvested "
                "area, cattle inventory, hog inventory, dairy production"
            ),
        },
        {
            "name": "EIA (Energy Information Administration)",
            "env": "BEDROCK_EIA_API_KEY",
            "url": "https://api.eia.gov/v2",
            "current_use": "WCESTUS1 (Crude Stocks), WGTSTUS1 (Gasoline), NW2_EPG0_SWO_R48_BCF (NatGas)",
            "available_more": (
                "Distillate stocks, propane stocks, ethanol, refinery "
                "utilization, refinery inputs (crude+gasoline runs), "
                "imports/exports, petroleum products supplied (demand "
                "proxy), natural gas processing, electricity demand"
            ),
        },
        {
            "name": "AGSI+ (EU Gas Storage)",
            "env": "BEDROCK_AGSI_API_KEY",
            "url": "https://agsi.gie.eu/api",
            "current_use": "EU-aggregat consumption_full_pct (current vs capacity)",
            "available_more": (
                "Per-land breakdown (DE, NL, IT, FR, AT, ES, PL etc.), "
                "withdrawal/injection rates, full vs working capacity, "
                "trend over time"
            ),
        },
        {
            "name": "FAS (Foreign Agricultural Service)",
            "env": "FAS_API_KEY",
            "url": "https://api.fas.usda.gov",
            "current_use": "Weekly export sales (CORN/SOYBEAN/WHEAT/COTTON)",
            "available_more": (
                "Production estimates per land, beginning stocks, "
                "domestic consumption, ending stocks, "
                "imports/exports per produkt"
            ),
        },
        {
            "name": "cTrader Open API (Spotware)",
            "env": "CTRADER_ACCESS_TOKEN",
            "url": "https://connect.spotware.com",
            "current_use": "Live priser via bot (kun runtime, ikke lagret)",
            "available_more": (
                "Historiske 1m/5m/15m/1h/D candles, depth-of-book, "
                "trade-history, deals-history (eget regnskap). "
                "Disse kan loaststs til DB for backtest hvis ønsket"
            ),
        },
        {
            "name": "Yahoo Finance",
            "env": "(ingen key — public)",
            "url": "https://query1.finance.yahoo.com",
            "current_use": "Daily price-data for alle 22 instrumenter via yfinance",
            "available_more": (
                "Intraday 1m/5m/15m/1h (siste 60 dager max for 1m), "
                "options chains (volatilitet-skew), earnings dates, "
                "dividend history (for indeks-konstruksjoner)"
            ),
        },
        {
            "name": "USGS Earthquake (seismic)",
            "env": "(ingen key — public)",
            "url": "https://earthquake.usgs.gov/fdsnws/event/1",
            "current_use": "Mag ≥ 4.5 siste 7 dager, mining-region-mapped",
            "available_more": (
                "Tilbake til 1900 (M ≥ 4.0), GeoJSON med detaljerte metadata (depth, rms, quality)"
            ),
        },
        {
            "name": "ICE Public CSV (cot_ice)",
            "env": "(ingen key)",
            "url": "https://www.theice.com/marketdata/reports/cot",
            "current_use": "ICE Brent + Gasoil COT ukentlig",
            "available_more": "Cocoa, Coffee, Wheat, Sugar, Dubai 1st line (også på public CSV — kan utvides)",
        },
        {
            "name": "Forex Factory Calendar",
            "env": "(ingen key — JSON-feed)",
            "url": "https://faireconomy.media",
            "current_use": "Event-distance + High/Medium impact-events",
            "available_more": "Forecast/previous/actual-felt for surprise-driver (ikke implementert)",
        },
        {
            "name": "AAII Sentiment",
            "env": "(ingen key — public XLSX)",
            "url": "https://www.aaii.com/sentimentsurvey",
            "current_use": "Bullish/Bearish % weekly",
            "available_more": "Historisk neutral-andel + 8-week-MA (kunne brukes for divergens-driver)",
        },
        {
            "name": "ESMIS (USDA WASDE)",
            "env": "(ingen key — XML-feed)",
            "url": "https://usda.library.cornell.edu",
            "current_use": "Månedlige supply/use-tabeller for 6 commodities",
            "available_more": "Monthly Coffee/Cocoa via separate WASDE-segment (ikke pulled)",
        },
        {
            "name": "BDRY ETF (Yahoo proxy for BDI)",
            "env": "(ingen key)",
            "url": "yahoo!Finance",
            "current_use": "Baltic Dry Index proxy (ikke direkte BDI)",
            "available_more": "Direkte BDI fra Baltic Exchange er kommersielt; BDRY er gratis approximation (~0.9 corr)",
        },
        {
            "name": "Cecafé (Brazil coffee)",
            "env": "(ingen key)",
            "url": "https://www.cecafe.com.br",
            "current_use": "Månedlig PDF-skraping for eksport-volum",
            "available_more": "Per-region (Sul de Minas, Cerrado etc.), per-grade differensial",
        },
        {
            "name": "Conab (Brazil agri)",
            "env": "(ingen key)",
            "url": "https://www.conab.gov.br",
            "current_use": "Årlige produksjon-estimater for Soybean/Corn/Coffee",
            "available_more": "Cotton, Sugar, månedlige Crop Progress-rapporter",
        },
        {
            "name": "USDM (Drought Monitor)",
            "env": "(ingen key — CSV)",
            "url": "https://droughtmonitor.unl.edu",
            "current_use": "CONUS-aggregat ukentlig",
            "available_more": "Per-state breakdown (Iowa for corn, Texas for cotton, California for almonds, etc.)",
        },
    ]
    # Sjekk hvilke keys faktisk er satt
    env_present = {}
    if SECRETS_FILE.exists():
        text = SECRETS_FILE.read_text(errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                key = line.split("=", 1)[0].strip()
                env_present[key] = True
    for s in sources:
        env = s["env"]
        if env.startswith("(") or env in os.environ or env in env_present:
            s["key_set"] = True
        else:
            s["key_set"] = False
    return sources


def main() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = OUT_DIR / f"data_utilization_report_{today}.md"

    table_stats = get_table_stats()
    driver_table_refs = find_table_references_in_drivers()
    lookback_params = get_lookback_params()
    apis = list_external_apis()

    lines: list[str] = []

    def w(s: str = "") -> None:
        lines.append(s)

    w(f"# Data-utnyttelse-rapport — {today}")
    w()
    w(f"**Generert:** {datetime.now(timezone.utc).isoformat()}")
    w(
        f"**SQLite-DB:** `{DB_PATH}` ({sum(t['rows'] for t in table_stats):,} rader på tvers av {len(table_stats)} tabeller)"
    )
    w()
    w("Komplementær til `driver_balance_report` — fokuserer på data-")
    w("siden: hva henter vi inn, hva bruker vi, hvilke kilder kan vi ")
    w("utvide til.")
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # 1. SQLite-tabeller
    # ──────────────────────────────────────────────────────────
    w("## 1. SQLite-tabeller — innhold + driver-bruk")
    w()
    w("Alle tabeller i `data/bedrock.db` med rad-antall, tids-vindu (hvis ")
    w("relevant tids-kolonne finnes) og hvilke drivere som leser fra dem. ")
    w("Tabeller uten driver-bruk er datakilder vi ikke utnytter scoring-")
    w("messig — de kan likevel være input til UI eller andre drivere.")
    w()
    w("| Tabell | Rader | Tids-kolonne | Min..Max | Drivere som leser |")
    w("|---|---:|---|---|---|")

    # Bygg reverse: tabell-navn → liste av drivere som leser
    table_to_drivers: dict[str, list[str]] = defaultdict(list)
    for drv, tables in driver_table_refs.items():
        for t in tables:
            # store.get_X → kan matche tabell-navn X eller TABLE_X-konstanten
            table_to_drivers[t].append(drv)

    for t in table_stats:
        # Heuristisk match: tabell-navn 'fundamentals' → store.get_fundamentals
        # Sjekk at vi har minst én driver som ber om denne
        readers = []
        for getter, drvs in table_to_drivers.items():
            if (
                getter == t["table"]
                or getter == t["table"].rstrip("s")
                or t["table"].startswith(getter)
            ):
                readers.extend(drvs)
        readers = sorted(set(readers))
        readers_str = ", ".join(readers) if readers else "_(ikke brukt)_"
        date_range = ""
        if t["date_min"] and t["date_max"]:
            date_range = f"{t['date_min']}..{t['date_max']}"
        w(
            f"| `{t['table']}` | {t['rows']:,} | {t['time_col'] or '–'} | "
            f"{date_range or '–'} | {readers_str} |"
        )
    w()

    unused_tables = [
        t["table"]
        for t in table_stats
        if not any(
            getter == t["table"] or t["table"].startswith(getter) for getter in table_to_drivers
        )
    ]
    if unused_tables:
        w(f"**{len(unused_tables)} tabeller har ingen driver-lesere (per regex-skann):** ")
        w(f"`{', '.join(unused_tables)}`")
        w()
        w("**Caveat — regex-detektoren har false-positive:** drivere som ")
        w("leser via custom helper-modul (eks. `find_analog_cases` fra ")
        w("`bedrock.data.analog`) i stedet for direkte `store.get_*` ")
        w("blir ikke fanget. Manuell verifisering anbefales:")
        w()
        w("- `analog_outcomes` (138k rader): **brukes** av `analog_hit_rate`+`analog_avg_return` ")
        w("  via `find_analog_cases` (regex-miss)")
        w("- `shipping_indices` (2,899 rader): **brukes** av `bdi_chg30d`")
        w("- `crypto_sentiment` (34 rader): **ikke brukt** — kandidat for ny driver")
        w(
            "- `news_intel` (102 rader): **ikke brukt** — kun UI-rendering, kandidat for sentiment-driver"
        )
        w("- `igc` (0 rader): **tom** — fetcher droppet eller ikke kjørt")
        w(
            "- `driver_observations` (453k), `feature_snapshots` (23k), `signal_setups` (26k): **meta-internal** (harvesting + persistens), ikke driver-input"
        )
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # 2. Per-driver data-kilder
    # ──────────────────────────────────────────────────────────
    w("## 2. Per-driver data-kilder")
    w()
    w("For hver driver: hvilke `store.get_*`-kall den gjør (= hvilke ")
    w("tabeller den leser). Drivere uten data-kall er rene tekniske/")
    w("matematiske transformasjoner over input-params.")
    w()
    w("| Driver | Tabeller (via store.get_*) |")
    w("|---|---|")
    for drv in sorted(driver_table_refs.keys()):
        tables = sorted(driver_table_refs[drv])
        w(f"| `{drv}` | {', '.join(tables) if tables else '_(ingen)_'} |")
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # 3. Historikk-utnyttelse
    # ──────────────────────────────────────────────────────────
    w("## 3. Historikk-utnyttelse — har vs bruker")
    w()
    w("For drivere med eksplisitt `lookback_*` eller `window_*`-")
    w("parameter: sammenlign default-verdi (rader brukt per kall) ")
    w("mot DB-historikk-dybde for relevant tabell. Stort gap = ")
    w("muligheter for langsiktige-features.")
    w()
    w("| Driver | Lookback-default | Tabeller | Tilgjengelig dybde | Utnyttelse |")
    w("|---|---|---|---|---|")
    for drv, lbs in sorted(lookback_params.items()):
        if not lbs:
            continue
        tables = sorted(driver_table_refs.get(drv, set()))
        # Få total dybde fra første tabell
        depth = "–"
        for t in table_stats:
            if t["table"] in tables or any(t["table"].startswith(x) for x in tables):
                if t["date_min"] and t["date_max"]:
                    try:
                        d_min = datetime.fromisoformat(str(t["date_min"]).split("T")[0])
                        d_max = datetime.fromisoformat(str(t["date_max"]).split("T")[0])
                        depth = f"{(d_max - d_min).days // 365}y ({t['rows']:,} rader)"
                    except (ValueError, TypeError):
                        depth = f"{t['rows']:,} rader"
                    break
        for param, default in sorted(set(lbs)):
            unit = "uker" if "week" in param else "dager" if "day" in param else "rader"
            usage_pct = "–"
            w(
                f"| `{drv}` | `{param}={default}` ({unit}) | "
                f"{', '.join(tables) or '–'} | {depth} | {usage_pct} |"
            )
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # 4. Eksterne API-kilder
    # ──────────────────────────────────────────────────────────
    w("## 4. Eksterne API-kilder — tilgjengelig + utnyttet")
    w()
    w("Alle kjente eksterne datakilder med vurdering av dagens bruk ")
    w("og hva mer som er tilgjengelig (med samme keys / public). ")
    w("Kandidater for nye drivere er linjene i 'Tilgjengelig mer'-")
    w("kolonnen.")
    w()
    for s in apis:
        key_status = "✓ key satt" if s.get("key_set") else "✗ ingen key"
        if s["env"].startswith("("):
            key_status = "(public, ingen key)"
        w(f"### {s['name']}")
        w()
        w(f"- **URL:** {s['url']}")
        w(f"- **Auth:** `{s['env']}` ({key_status})")
        w(f"- **I bruk i dag:** {s['current_use']}")
        w(f"- **Tilgjengelig mer:** {s['available_more']}")
        w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # 5. Arkitektur-sjekk
    # ──────────────────────────────────────────────────────────
    w("## 5. Arkitektur — er det enkelt å legge til/fjerne drivere?")
    w()
    w("**Ja, arkitekturen er bygd for det.** Per `docs/driver_authoring.md`:")
    w()
    w("### Legge til en driver (eks. ny FRED-serie):")
    w()
    w("1. Skriv funksjon i `src/bedrock/engine/drivers/<kategori>.py`:")
    w("   ```python")
    w('   @register("my_new_driver")')
    w("   def my_new_driver(store, instrument, params):")
    w('       series = store.get_fundamentals("MY_FRED_ID", lookback=...)')
    w("       return clip(z_score(series), 0, 1)")
    w("   ```")
    w("2. Oppdater fetch.yaml hvis ny datakilde må hentes:")
    w("   ```yaml")
    w("   fundamentals:")
    w("     fred_series_ids:")
    w("       - MY_FRED_ID")
    w("   ```")
    w("3. Wire inn i instrument-YAML:")
    w("   ```yaml")
    w("   families:")
    w("     macro:")
    w("       drivers:")
    w("         - {name: my_new_driver, weight: 0.3, horizons: [MAKRO]}")
    w("   ```")
    w("4. Re-generer baseline + signals:")
    w("   ```")
    w("   .venv/bin/python scripts/snapshot/score_baseline.py")
    w("   .venv/bin/bedrock signals-all")
    w("   ```")
    w()
    w("**Ingen kjerne-kode-endringer.** Engine slår opp via registry-")
    w("dict; YAML-felt valideres av Pydantic uten hardkodede driver-")
    w("navn-listinger noe sted.")
    w()
    w("### Fjerne en driver (eks. for å slanke en familie):")
    w()
    w("1. Slett driver-entryen fra instrument-YAML(ene)")
    w("2. (Valgfritt) Slett funksjonen fra `drivers/*.py` hvis ingen ")
    w("   andre instrumenter bruker den")
    w("3. Re-generer baseline")
    w()
    w("Ingen migrasjons-script trengs — Pydantic-validering fanger ")
    w("dangling-references ved oppstart.")
    w()
    w("### Verifisert i denne sessionen:")
    w()
    w("- Sub-fase 12.9 Fase 3 la til `horizons:`-felt på DriverSpec ")
    w("  uten å touche kjerne-engine-loops")
    w("- Sub-fase 12.5+ session 138 droppet 2 dead-drivere ")
    w("  (`currency_cross_trend`, `igc_stocks_change`) ved kun YAML-")
    w("  fjern + slette driver-fil. Ingen migrasjons-arbeid.")
    w("- 17 drivere fikk horisont-filter via 1-fils YAML-script ")
    w("  (`/tmp/migrate_horizons.py`). Lap-tid ~3 sek.")
    w()
    w("---")
    w()

    # ──────────────────────────────────────────────────────────
    # 6. Anbefalte data-utvidelser
    # ──────────────────────────────────────────────────────────
    w("## 6. Anbefalte data-utvidelser (kandidat-drivere)")
    w()
    w("Basert på Seksjon 4: kilder vi har tilgang til men ikke ")
    w("utnytter. Sortert etter forventet IC og tilgjengelighet. ")
    w("Implementasjon estimat-time = ~2-4 timer per driver inkl. ")
    w("schema + fetcher + driver + tester.")
    w()
    w("| Prioritet | Driver-idé | Kilde | Bruk |")
    w("|---|---|---|---|")
    w(
        "| **HØY** | `industrial_production_yoy` | FRED INDPRO | Macro-regime confirmation, korrelert med Copper/CrudeOil-prising |"
    )
    w("| **HØY** | `ism_pmi` | FRED NAPM | Manufacturing PMI; ledende indikator for risk-on/off |")
    w(
        "| **HØY** | `umich_consumer_sentiment` | FRED UMCSENT | Tidlig sentiment-skifte, swing-driver |"
    )
    w(
        "| **HØY** | `forecast_surprise` (NFP/CPI) | calendar_ff forecast/actual | Scalp-trigger ved release |"
    )
    w("| **MED** | `eia_distillate_change` | EIA series | NatGas/Brent supply-side, ukentlig |")
    w("| **MED** | `nass_yields_yoy` | USDA NASS | Agri yield-estimat-divergens |")
    w("| **MED** | `agsi_per_country` | AGSI per-land | NatGas regional supply (DE/NL/IT) |")
    w("| **MED** | `usdm_per_state` | USDM per-stat | Cotton (TX), Corn (IA) — mer presist |")
    w("| **LAV** | `seismic_global_M6_24h` | USGS | Real-time scalp-trigger, sjelden |")
    w(
        "| **LAV** | `cot_ice_cocoa/coffee/sugar` | ICE Public CSV | Allerede pulled, bare wire driver |"
    )
    w("| **LAV** | `vix_options_skew` | Yahoo VIX9D vs VIX | Volatilitet-skew som scalp-bias |")
    w()
    w("**Ikke-anbefalt:** Kommersielle kilder (Bloomberg, Reuters, ")
    w("LSEG, ICE Premium). Bedrock-prinsipp er gratis-kilder + manuell ")
    w("CSV-fallback der HTTP feiler (ADR-007).")
    w()
    w("---")
    w()
    w(f"_Generert av_ `scripts/analysis/data_utilization_report.py` _på {today}._")
    w()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rapport skrevet til: {out_path}")
    print(
        f"Tabeller: {len(table_stats)}, Drivere med data-kall: {len(driver_table_refs)}, Eksterne kilder: {len(apis)}"
    )
    return out_path


if __name__ == "__main__":
    main()
