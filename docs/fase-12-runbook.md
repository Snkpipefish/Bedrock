# Fase 12 — Parallell-drift runbook

Denne rutinen aktiverer parallell-drift mellom bedrock og det gamle
systemet (cot-explorer + scalp_edge), per PLAN § 12.

**Viktig:** Cot-explorer-timere skal ikke skrus av før Fase 13 cutover
er bekreftet. Begge systemer kjører samtidig under hele Fase 12.

---

## Oversikt

Fase 12 = 2 ukers demo-parallell-drift. Tre infrastruktur-komponenter
ble levert i session 66 (opening-session):

1. **Systemd-timer-installasjon** for bedrock-fetchere
   (`bedrock systemd generate` + `install`).
2. **Daglig signal-diff-script** —
   `scripts/compare_signals_daily.py` (logikk i
   `bedrock.parallel.compare`).
3. **Pipeline-monitor-script** —
   `scripts/monitor_pipeline.py` (logikk i
   `bedrock.parallel.monitor`).

Aktiveringen av parallell-drift er en separat session (67+) som
faktisk kjører `systemctl --user enable --now`.

---

## A. Aktivere bedrock fetch-timere

### A.1 Generer unit-filer

```bash
cd ~/bedrock
PYTHONPATH=src .venv/bin/python -m bedrock.cli systemd generate \
    --output systemd \
    --working-dir ~/bedrock \
    --executable ~/bedrock/.venv/bin/bedrock
```

Skriver `bedrock-fetch-<name>.service` + `bedrock-fetch-<name>.timer`
for hver fetcher i `config/fetch.yaml` til `systemd/`-mappen i repo.

Verifiser:

```bash
PYTHONPATH=src .venv/bin/python -m bedrock.cli systemd list
```

### A.2 Tørrkjør install

```bash
PYTHONPATH=src .venv/bin/python -m bedrock.cli systemd install \
    --units-dir systemd \
    --dry-run
```

Viser hver `systemctl --user link`-kommando uten å kjøre dem. Sjekk
at stiene ser riktige ut.

### A.3 Faktisk install (når du er klar for parallell-drift)

```bash
PYTHONPATH=src .venv/bin/python -m bedrock.cli systemd install \
    --units-dir systemd

systemctl --user daemon-reload
```

`install` linker hver unit-fil inn i `~/.config/systemd/user/`.
`daemon-reload` får systemd til å plukke opp endringene.

### A.4 Aktiver hver timer enkeltvis

Aktiver én og én — ikke alle samtidig — slik at du kan se eventuelle
feil per fetcher før neste startes.

```bash
systemctl --user enable --now bedrock-fetch-prices.timer
systemctl --user enable --now bedrock-fetch-cot_disaggregated.timer
systemctl --user enable --now bedrock-fetch-cot_legacy.timer
systemctl --user enable --now bedrock-fetch-fundamentals.timer
systemctl --user enable --now bedrock-fetch-weather.timer
systemctl --user enable --now bedrock-fetch-enso.timer
```

Sjekk status:

```bash
systemctl --user list-timers --all
journalctl --user -u bedrock-fetch-prices --since '10 min ago'
```

### A.5 Dry-run-modus per PLAN § 12.1

PLAN § 12.1 sier "Bedrock-systemd-timer kjører i `--dry-run` (skriver
signals men POST-er ikke til signal_server)".

Fetch-timerne skriver til `data/bedrock.db` og utløser ikke
signal_server-POST direkte — POST-flyten kjører via en separat
publishing-pipeline som **ikke aktiveres** i Fase 12. Det betyr at
fetch-timerne i praksis kjører "produksjon for data, dry-run for
publish" allerede.

Når en signals-publishing-timer legges til (Fase 12 sub-session), må
den eksplisitt ha `--dry-run` eller en config-flagg som blokkerer
POST.

---

## B. Daglig signal-diff

`scripts/compare_signals_daily.py` sammenligner bedrock signals.json
mot cot-explorers `signals.json` + `agri_signals.json`. Join-nøkkel
er `(instrument lower, horizon lower, direction lower)`.

### B.1 Manuell kjøring

```bash
cd ~/bedrock
PYTHONPATH=src .venv/bin/python scripts/compare_signals_daily.py
```

Default-input:

- Bedrock: `data/signals.json`
- Gammel: `~/cot-explorer/data/signals.json`
  + `~/cot-explorer/data/agri_signals.json`

Skriv rapport til fil:

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_signals_daily.py \
    --output data/_meta/compare_$(date +%F).md
```

### B.2 Tolkning

| Kategori | Betydning | Handling |
|---|---|---|
| Felles | Begge systemer enige om instrument/horizon/direction | Sjekk grade og score-pct |
| Kun gammel | Bedrock mangler signal | Forventet hvis bedrock ikke har konfig for det instrumentet ennå |
| Kun bedrock | Gammelt system mangler signal | Bedrock har funnet noe det gamle ikke fanget — flagg for review |
| Endret | Felles men ulik grade/score/entry/sl | Forklar i terminoer av regelendringer eller data-diff |

Toleranser:
- Score normalisert til `score/max_score`. Tolerer 5 prosentpoeng
  forskjell.
- Entry/SL: relativ toleranse 0.1 % (0.001).

### B.3 JSON-output for audit

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_signals_daily.py \
    --report json \
    --output data/_meta/compare_$(date +%F).json
```

---

## C. Pipeline-monitor

`scripts/monitor_pipeline.py` automatiserer 4 av 5 PLAN § 12.3
cutover-kriterier.

### C.1 Manuell kjøring

```bash
cd ~/bedrock
PYTHONPATH=src .venv/bin/python scripts/monitor_pipeline.py
```

Eksit-kode:
- 0 = alle delsjekker OK
- 1 = minst én delsjekk feilet

### C.2 Sjekkene

| Delsjekk | PLAN § 12.3 | OK-kriterium |
|---|---|---|
| `fetcher_freshness` | #1 (proxy) | Ingen fetchere er `stale` eller `missing` |
| `pipeline_log_errors` | #2 | 0 feil-keywords i siste 1000 linjer av `logs/pipeline.log` |
| `agri_tp_override` | #3 | 0 treff på "agri TP overridden" i siste 5000 linjer av `~/scalp_edge/bot.log` |
| `signal_diff` | #4 | Andel grade-endringer < 50 % av felles signaler |
| **Manuelt** | #5 | Inspiser siste 20 publiserte setups (entry, TP, R:R) |

### C.3 Som systemd-timer (anbefalt)

For å kjøre monitoren daglig kl 06:30 lokal tid:

`~/.config/systemd/user/bedrock-monitor.service`

```ini
[Unit]
Description=Bedrock parallell-drift monitor
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/bedrock
Environment=PYTHONPATH=%h/bedrock/src
ExecStart=%h/bedrock/.venv/bin/python scripts/monitor_pipeline.py \
    --report json \
    --output %h/bedrock/data/_meta/monitor_%Y-%m-%d.json
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

`~/.config/systemd/user/bedrock-monitor.timer`

```ini
[Unit]
Description=Daily bedrock monitor

[Timer]
OnCalendar=*-*-* 06:30:00
Persistent=true
Unit=bedrock-monitor.service

[Install]
WantedBy=timers.target
```

Aktiver:

```bash
systemctl --user daemon-reload
systemctl --user enable --now bedrock-monitor.timer
```

(Disse to filene kan auto-genereres fra fetch.yaml-mønsteret hvis
det blir aktuelt med flere monitor-jobber. Ikke prioritert nå.)

---

## D. Rollback

Hvis noe går galt under aktivering, slå av bedrock-timerne med:

```bash
systemctl --user disable --now bedrock-fetch-prices.timer
systemctl --user disable --now bedrock-fetch-cot_disaggregated.timer
# ... osv per timer
```

For å fjerne alle bedrock-units helt:

```bash
for unit in ~/.config/systemd/user/bedrock-fetch-*; do
    systemctl --user disable --now $(basename "$unit") 2>/dev/null
    rm "$unit"
done
systemctl --user daemon-reload
```

Cot-explorer-timerne påvirkes ikke av dette og fortsetter å kjøre.

---

## E. Cutover-kriterier (PLAN § 12.3)

Etter 2 uker parallell-drift, evaluer:

- [ ] `monitor_pipeline.py` returnerer exit 0 minst 5 dager på rad
- [ ] `compare_signals_daily.py` viser grade-diff < 50 % på felles
      signaler 5 dager på rad
- [ ] Ingen unexpected exceptions i siste 14 dagers monitor-output
- [ ] Bot-log viser 0 "agri TP overridden" siste 14 dager
- [ ] Manuelt review av siste 20 publiserte setups: entry-nivå
      reelt, TP ved reelt nivå, R:R ≥ horisont-min

Når alle er ✅ → Fase 13 cutover (skru av cot-explorer-timere).

---

## F. Status-kommandoer

```bash
# Hvilke bedrock-timere er aktive?
systemctl --user list-timers 'bedrock-*'

# Når kjørte prices sist?
systemctl --user list-timers bedrock-fetch-prices.timer

# Hva skjedde i siste prices-kjøring?
journalctl --user -u bedrock-fetch-prices.service -n 50

# Feilet noen kjøring siste døgn?
journalctl --user -u 'bedrock-*' --since yesterday | grep -i 'error\|fail'
```
