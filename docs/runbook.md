# Runbook — incident playbook

Stub. Utfylles gradvis etter hvert som pipelinen tas i bruk og incidents dukker opp.

## Generelle prinsipper

1. **Først: sjekk STATE.md og logger.** Ofte er det åpenbart hva som feilet.
2. **Ikke force-push til main.** Heller revert-commit med forklaring.
3. **Kill-switch er trygt å bruke.** `bedrock kill all` stopper nye trades mens du undersøker.

## Vanlige scenarioer

### Pipeline hopper over én kjøring

Sjekk:
- `data/_meta/pipeline_health.json` — siste vellykkede kjøring
- `logs/pipeline.log` — siste feil
- Systemd: `systemctl status bedrock-main.service`

### Signal_server svarer ikke

```bash
systemctl status bedrock-server.service
journalctl -u bedrock-server -n 100
```

Typiske årsaker: port 5000 i bruk av noe annet, SCALP_API_KEY mismatch.

### Bot har mistet forbindelse til cTrader

```bash
tail -n 200 logs/bot.log | grep -i "reconnect\|protobuf\|ssl"
```

Auto-reconnect håndterer de fleste tilfeller. Hvis ikke: restart service.

### Git-push feiler kontinuerlig

Vanlige årsaker:
- CA-cert-problemer: `sudo apt install --reinstall ca-certificates`
- Non-fast-forward: en annen process pushet først. Rebase og prøv igjen.
- Credentials utløpt: refresh GitHub-token.

### Kill-switch

```bash
# Stopp alle åpne trades og blokker nye
bedrock kill all

# Stopp én spesifikk
bedrock kill sig_abc123

# Resume
bedrock resume
```

## Rollback til forrige fase-tag

```bash
git checkout main
git log --oneline -20                # finn siste gode commit eller tag
git revert <problemcommit>           # trygt — ingen historie-endring
git push
```

Eventuelt checkout tidligere tag for testing:
```bash
git checkout v0.1.0-fase-1
# inspiser, test — IKKE commit her
git checkout main
```
