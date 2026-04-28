"""CONAB Café-historikk-backfill — selvstendig nedlaster + ingester.

Sub-fase 12.6 fix § 3 (2026-04-28): café-historikken er en separat boletim-
serie hos CONAB (`gov.br/conab/.../safra-de-cafe`) som ikke er med i
grains-Excelene fra session 118. Fetcher (`bedrock/fetch/conab.py:196`)
finner kun siste levantamento — for full historikk trengs URL-pattern-
gjetting + sekvensiell PDF-nedlasting.

Idempotent + sekvensiell + retry-med-backoff. Designet for å kjøres detached
via `scripts/run_backfill.sh cafe-history start`. Logger til
`data/_meta/backfill_cafe_history.log`.

Scope:
  Phase 1 — DOWNLOAD: scrape index + probe URLer for safra 2017-2026 ×
  levantamento 1-4. Lagre PDF-er i `bedrock manuell data/cafe_boletins/`.
  Hopper over PDF-er som allerede er på disk.

  Phase 2 — INGEST: parse alle PDF-er i mappen, skriv til DB-tabell
  `conab_estimates`. Hopper rader som allerede finnes (PK report_date+
  commodity).

Bruk:
  PYTHONPATH=src .venv/bin/python scripts/backfill_conab_cafe.py
  PYTHONPATH=src .venv/bin/python scripts/backfill_conab_cafe.py --download-only
  PYTHONPATH=src .venv/bin/python scripts/backfill_conab_cafe.py --ingest-only

Eksitkode:
  0  alt OK
  1  download- eller ingest-feil (sjekk loggen)
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from collections.abc import Iterable
from pathlib import Path

import requests

from bedrock.data.store import DataStore
from bedrock.fetch.conab import (
    extract_levantamento,
    parse_cafe,
    pdf_to_text,
)

# ---------------------------------------------------------------------------
# Konstanter
# ---------------------------------------------------------------------------

CAFE_INDEX = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe"
LEV_URL_TEMPLATE = (
    "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias"
    "/safras/safra-de-cafe/{n}o-levantamento-de-cafe-safra-{year}"
    "/{n}o-levantamento-de-cafe-safra-{year}"
)

DEFAULT_OUTPUT_DIR = Path("bedrock manuell data/cafe_boletins")
DEFAULT_LOG_FILE = Path("data/_meta/backfill_cafe_history.log")
DEFAULT_DB = Path("data/bedrock.db")

YEAR_RANGE = range(2017, 2027)  # safra-årene CONAB sannsynligvis har
LEVANTAMENTO_RANGE = range(1, 5)  # 4 levantamentos per safra-år (1-4)
PACING_SECONDS = 15.0  # mellom PDF-nedlastninger (CONAB throttler aggressivt)
PROBE_PACING = 8.0  # mellom probe-requests — testet at 5s ble blokkert med 403
HTTP_TIMEOUT = 30.0
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) bedrock-backfill/0.1"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
RETRY_STATUSES = {429, 500, 502, 503, 504}
THROTTLE_STATUSES = {403, 429}  # 403 = CONAB rate-limiter
MAX_RETRIES = 3
THROTTLE_BACKOFF_BASE = 60.0  # ved 403/429: vent 60s, deretter 120, 240


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _setup_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("conab_cafe_backfill")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger  # idempotent
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


# ---------------------------------------------------------------------------
# HTTP-helpere
# ---------------------------------------------------------------------------


def _get_with_retry(
    url: str,
    log: logging.Logger,
    *,
    timeout: float = HTTP_TIMEOUT,
) -> requests.Response | None:
    """GET med backoff på 403/429/5xx. None hvis alle retries feiler.

    403 fra CONAB betyr ofte rate-limiter, ikke permanent forbud — vi
    venter THROTTLE_BACKOFF_BASE sek og prøver igjen. Hvis 3x 403 på rad,
    gi opp denne URL-en (caller logger og fortsetter).
    """
    delay = PACING_SECONDS
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        except requests.RequestException as exc:
            log.warning("GET %s failed (attempt %d): %s", url, attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
            continue
        if r.status_code == 200:
            return r
        if r.status_code == 404:
            return r  # ikke retry, men return så caller kan inspisere
        if r.status_code in THROTTLE_STATUSES and attempt < MAX_RETRIES:
            wait = THROTTLE_BACKOFF_BASE * (2 ** (attempt - 1))
            log.warning(
                "GET %s → %d (throttled), backoff %.0fs (attempt %d/%d)",
                url,
                r.status_code,
                wait,
                attempt,
                MAX_RETRIES,
            )
            time.sleep(wait)
            continue
        if r.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
            log.warning("GET %s → %d, retry %d", url, r.status_code, attempt)
            time.sleep(delay)
            delay *= 2
            continue
        return r
    return None


# ---------------------------------------------------------------------------
# Phase 1: DOWNLOAD
# ---------------------------------------------------------------------------


def _extract_pdf_links_from_lev_page(html: str) -> list[str]:
    """Returnerer absolutte URL-er som peker til café-boletim-PDF-er.

    CONAB Plone serverer PDF-er via katalog-URL UTEN .pdf-suffix (f.eks.
    `boletim-cafe-dezembro-2025`). Vi matcher derfor på navne-mønsteret
    "boletim-cafe-..." istedenfor file-extension. Tabela-data-lenker
    (Excel) ekskluderes eksplisitt.
    """
    pdfs: list[str] = []
    # Mønster 1: rene .pdf-filer (eldre kataloger eller direktelenker)
    for match in re.findall(r'href=["\']([^"\']+\.pdf)["\']', html):
        if "cafe" in match.lower() or "boletim-de-safras" in match.lower():
            url = match if match.startswith("http") else f"https://www.gov.br{match}"
            if url not in pdfs:
                pdfs.append(url)

    # Mønster 2: Plone-katalog-lenker uten suffix — boletim-cafe-{måned}-{år}
    # Vi vil prioritere boletim foran tabela-de-dados (Excel).
    plone_pattern = re.compile(
        r'href=["\']([^"\']*?/boletim-cafe-[^"\']+?)["\']',
        re.IGNORECASE,
    )
    for match in plone_pattern.findall(html):
        # Skip tabela-data og andre ikke-PDF-ressurser
        if "tabela-de-dados" in match.lower() or "estimativas" in match.lower():
            continue
        url = match if match.startswith("http") else f"https://www.gov.br{match}"
        if url not in pdfs:
            pdfs.append(url)

    return pdfs


def _candidate_levantamento_urls() -> Iterable[tuple[int, int, str]]:
    """Yielder (safra-år, levantamento-nr, URL) for alle kombinasjoner.

    Året i URL er kalenderåret levantamento publiseres (= safra-året).
    """
    for year in YEAR_RANGE:
        for n in LEVANTAMENTO_RANGE:
            yield year, n, LEV_URL_TEMPLATE.format(n=n, year=year)


def _scrape_index_for_extra_levantamentos(
    log: logging.Logger,
) -> list[tuple[int, int, str]]:
    """Skrap index-siden for levantamento-URL-er som ikke matcher mal.

    Index-siden har vanligvis 4 siste levantamentos. Vi henter dem
    eksplisitt i tilfelle URL-mønsteret avviker (eldre safra-år har
    iblant `safra-de-cafe-1`, `safra-de-cafe-archive` etc.).
    """
    log.info("Scraping index: %s", CAFE_INDEX)
    r = _get_with_retry(CAFE_INDEX, log)
    if r is None or r.status_code != 200:
        log.warning("Index scrape failed (status=%s)", getattr(r, "status_code", "n/a"))
        return []

    pattern = re.compile(
        r'href=["\'](https://www\.gov\.br/conab/[^"\']*?/'
        r"(\d+)o-levantamento-de-cafe-safra-(\d+)/"
        r"\d+o-levantamento-de-cafe-safra-\d+)" + r'["\']'
    )
    found: list[tuple[int, int, str]] = []
    for url, lev_str, year_str in pattern.findall(r.text):
        try:
            year = int(year_str)
            n = int(lev_str)
        except ValueError:
            continue
        found.append((year, n, url))
    log.info("Index ga %d levantamento-lenker", len(found))
    return found


def download_pdf(url: str, dest: Path, log: logging.Logger) -> bool:
    """Last ned PDF til dest. True hvis ny, False hvis hoppet eller feilet.

    Plone serverer PDF via katalog-URL, så Content-Type er det som forteller
    om vi får PDF-bytes. Vi sjekker også %PDF-magic-bytes for ekstra
    sikkerhet (HTML 403-sider innehold ikke %PDF).
    """
    if dest.exists() and dest.stat().st_size > 0:
        log.info("SKIP %s (finnes: %s, %d bytes)", dest.name, dest, dest.stat().st_size)
        return False
    log.info("DOWNLOAD %s → %s", url, dest)
    r = _get_with_retry(url, log, timeout=120.0)
    if r is None or r.status_code != 200:
        log.error("PDF-nedlasting feilet (%s, status=%s)", url, getattr(r, "status_code", "n/a"))
        return False
    if not r.content or not r.content.startswith(b"%PDF"):
        ctype = r.headers.get("Content-Type", "?")
        log.error("Innhold er ikke PDF (%s, ctype=%s, første bytes=%r)", url, ctype, r.content[:8])
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    log.info("OK %s (%d bytes)", dest.name, len(r.content))
    return True


def run_download_phase(
    output_dir: Path,
    log: logging.Logger,
) -> tuple[int, int, int]:
    """Returner (forsøkt, lastet, hoppet)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[tuple[int, int, str]] = list(_candidate_levantamento_urls())
    extras = _scrape_index_for_extra_levantamentos(log)
    seen_urls = {url for _, _, url in candidates}
    for year, n, url in extras:
        if url not in seen_urls:
            candidates.append((year, n, url))
            seen_urls.add(url)

    log.info("Probing %d levantamento-kandidater", len(candidates))

    attempted = 0
    downloaded = 0
    skipped = 0

    for year, n, lev_url in sorted(candidates, key=lambda t: (t[0], t[1])):
        attempted += 1
        time.sleep(PROBE_PACING)
        r = _get_with_retry(lev_url, log)
        if r is None or r.status_code == 404:
            log.info("SKIP levantamento %do/safra-%d (URL 404 eller failed)", n, year)
            continue
        if r.status_code != 200:
            log.warning("levantamento %do/safra-%d uventet status=%d", n, year, r.status_code)
            continue
        pdf_urls = _extract_pdf_links_from_lev_page(r.text)
        if not pdf_urls:
            log.warning("Ingen PDF funnet på %do/safra-%d", n, year)
            continue
        # Velg den første som er en levantamento-PDF (filtrert allerede).
        pdf_url = pdf_urls[0]
        # Filnavn: bruk slug fra URL. Plone-lenker har ikke .pdf-suffix —
        # legg til så filsystemet ser det som PDF.
        slug = pdf_url.rsplit("/", 1)[-1]
        if not slug.lower().endswith(".pdf"):
            slug = f"{slug}.pdf"
        # Prefiks med safra+levantamento for sortering
        dest = output_dir / f"safra-{year}_{n}o_{slug}"
        time.sleep(PACING_SECONDS)
        if download_pdf(pdf_url, dest, log):
            downloaded += 1
        elif dest.exists():
            skipped += 1

    log.info(
        "Download-phase ferdig: %d forsøkt, %d lastet ned, %d hoppet",
        attempted,
        downloaded,
        skipped,
    )
    return attempted, downloaded, skipped


# ---------------------------------------------------------------------------
# Phase 2: INGEST
# ---------------------------------------------------------------------------


_FILENAME_RE = re.compile(r"safra-(\d{4})_(\d+)o[_-]")


def _parse_pdf_filename(fname: str) -> tuple[int, int] | None:
    m = _FILENAME_RE.search(fname)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def ingest_pdf(pdf_path: Path, store: DataStore, log: logging.Logger) -> int:
    """Parse én café-PDF og skriv til DB. Returner antall rader skrevet."""
    parsed_name = _parse_pdf_filename(pdf_path.name)
    if not parsed_name:
        log.warning("Kan ikke parse safra+levantamento fra filnavn: %s", pdf_path.name)
        return 0
    safra_year, lev_n = parsed_name

    try:
        pdf_bytes = pdf_path.read_bytes()
        text = pdf_to_text(pdf_bytes)
    except Exception as exc:
        log.error("PDF-text-extract feilet (%s): %s", pdf_path.name, exc)
        return 0
    if text is None:
        log.error("PDF-text-extract returnerte None (%s)", pdf_path.name)
        return 0

    cafe_data = parse_cafe(text)
    if not cafe_data:
        log.warning("Ingen café-tabeller i %s", pdf_path.name)
        return 0

    # Levantamento + safra fra PDF-teksten (mest pålitelig). Filnavn er
    # fallback hvis tekst-extract ikke finner.
    lev_str, safra_str = extract_levantamento(text)
    if not safra_str:
        safra_str = str(safra_year)
    levantamento_str = lev_str or f"{lev_n}o"

    # Approx report-date: CONAB café-cycle (jan / mai / sep / des)
    month_by_lev = {1: 1, 2: 5, 3: 9, 4: 12}
    report_date = f"{safra_year:04d}-{month_by_lev.get(lev_n, 1):02d}-15"

    rows = []
    for commodity, vals in cafe_data.items():
        production = vals.get("production")
        if production is None:
            continue
        rows.append(
            {
                "report_date": report_date,
                "commodity": commodity,
                "production": float(production),
                "production_units": vals.get("production_units") or "ksacas",
                "area_kha": vals.get("area_kha"),
                "yield_value": vals.get("yield_value"),
                "yield_units": vals.get("yield_units"),
                "levantamento": levantamento_str,
                "safra": safra_str,
                "yoy_change_pct": vals.get("yoy_change_pct"),
                "mom_change_pct": None,  # parse_cafe gir ikke MoM
            }
        )

    if not rows:
        log.warning("0 parse-able rader i %s", pdf_path.name)
        return 0

    import pandas as pd

    df = pd.DataFrame(rows)
    inserted = store.append_conab_estimates(df)
    log.info("INGEST %s: %d rader → DB (%d nye)", pdf_path.name, len(rows), inserted)
    return inserted


def run_ingest_phase(
    pdf_dir: Path,
    db_path: Path,
    log: logging.Logger,
) -> int:
    """Returner totalt antall nye rader skrevet."""
    if not pdf_dir.exists():
        log.warning("PDF-mappe finnes ikke: %s", pdf_dir)
        return 0

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    log.info("Ingest-fase: %d PDF-er funnet i %s", len(pdfs), pdf_dir)
    if not pdfs:
        return 0

    store = DataStore(str(db_path))
    total = 0
    for pdf in pdfs:
        try:
            total += ingest_pdf(pdf, store, log)
        except Exception as exc:
            log.exception("Ingest feilet for %s: %s", pdf.name, exc)
    log.info("Ingest-fase ferdig: %d nye rader totalt", total)
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Hvor PDF-er lagres (default: %(default)s)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="SQLite-DB for ingest (default: %(default)s)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_FILE,
        help="Log-fil (default: %(default)s)",
    )
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--ingest-only", action="store_true")
    args = parser.parse_args(argv)

    log = _setup_logging(args.log_file)
    log.info("=== Café-historikk-backfill startet ===")
    log.info(
        "Args: output_dir=%s db=%s download_only=%s ingest_only=%s",
        args.output_dir,
        args.db,
        args.download_only,
        args.ingest_only,
    )

    if args.download_only and args.ingest_only:
        log.error("--download-only og --ingest-only er mutually exclusive")
        return 1

    rc = 0

    if not args.ingest_only:
        try:
            attempted, downloaded, skipped = run_download_phase(args.output_dir, log)
            log.info(
                "DOWNLOAD-summary: %d kandidater probet, %d nye PDF-er, %d hoppet",
                attempted,
                downloaded,
                skipped,
            )
        except Exception as exc:
            log.exception("Download-fase krasjet: %s", exc)
            rc = 1

    if not args.download_only:
        try:
            new_rows = run_ingest_phase(args.output_dir, args.db, log)
            log.info("INGEST-summary: %d nye DB-rader", new_rows)
        except Exception as exc:
            log.exception("Ingest-fase krasjet: %s", exc)
            rc = 1

    log.info("=== Café-historikk-backfill ferdig (rc=%d) ===", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
