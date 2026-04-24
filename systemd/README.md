# Systemd-filer

Auto-genererte `.service` + `.timer`-filer for Bedrock fetch-pipeline.
**Ikke rediger manuelt** — de genereres fra `config/fetch.yaml` av
`bedrock systemd generate`.

## Regenerering etter endret fetch-config

```bash
bedrock systemd generate \
    --working-dir /home/pc/bedrock \
    --executable /home/pc/bedrock/.venv/bin/bedrock
```

(Uten flaggene brukes nåværende arbeidskatalog og auto-detected
`bedrock`-CLI fra `sys.prefix`/`PATH`.)

## Installering (per bruker — uten sudo)

```bash
# 1. Link inn unit-filene (peker fra ~/.config/systemd/user/ til repo)
bedrock systemd install

# 2. Last systemd-bruker-konfig
systemctl --user daemon-reload

# 3. Aktiver timere (én om gangen eller alle):
systemctl --user enable --now bedrock-fetch-prices.timer
systemctl --user enable --now bedrock-fetch-cot_disaggregated.timer
systemctl --user enable --now bedrock-fetch-cot_legacy.timer
systemctl --user enable --now bedrock-fetch-fundamentals.timer
systemctl --user enable --now bedrock-fetch-weather.timer
```

## Status-sjekker

```bash
# Liste over aktive timere
systemctl --user list-timers bedrock-fetch-*

# Logs for én fetcher
journalctl --user -u bedrock-fetch-prices.service

# Siste kjøring
systemctl --user status bedrock-fetch-prices.timer
```

## Inspeksjon uten å installere

```bash
# Vis hva som ville blitt kjørt
bedrock systemd install --dry-run

# Vis gjeldende OnCalendar-tider
bedrock systemd list
```

## Kilde

`bedrock systemd generate` leser `config/fetch.yaml`-cronstrengene og
oversetter til `OnCalendar=`-syntaks. Støttet cron-undersett:

- `*` og spesifikke heltall i alle felter
- `A-B` eller `A,B,C` i dow-felt
- Søndag som både `0` og `7`

Ikke støttet (enn så lenge): `*/N` step-values, navngitte måneder/dager.

## Timere i prod

Etter session 30 er følgende timere generert:

- `bedrock-fetch-prices.timer` — hverdager hver time :40
- `bedrock-fetch-cot_disaggregated.timer` — fredager 22:00 UTC
- `bedrock-fetch-cot_legacy.timer` — fredager 22:00 UTC
- `bedrock-fetch-fundamentals.timer` — daglig 02:30 UTC
- `bedrock-fetch-weather.timer` — daglig 03:00 UTC

Hver timer kaller en `.service` som kjører `bedrock fetch run <name>`.
Oppretter seg per-instrument iterasjon + per-item resiliens fra
session 29.

## Senere (Fase 11 cutover)

Andre timere for signal-pipeline, bot og server kommer når disse
komponentene er refaktorert (PLAN § 8-9). De vil følge samme mønster
og kan genereres på samme vis.
