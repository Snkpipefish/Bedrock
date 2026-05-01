# data/bot/ — bedrock-bot runtime-state

Filer i denne mappen er **ikke** kildekontrollert (se .gitignore).
De persisteres lokalt for review og resilience over restart.

## Filer

| Fil | Innhold | Skriver |
|---|---|---|
| `signal_log.json` | Closed trades (JSON-array, full historikk siden bot-start) | `bedrock.bot.exit.ExitEngine._append_trade_log` |
| `trade_log.jsonl` | (alternativ jsonl-format hvis eldre versjon brukes) | samme |
| `daily_loss_state.json` | `{date, daily_loss}` for daglig PnL-rollover | `SafetyMonitor` |
| `agri_symbol_info.json` | cTrader symbol-id mapping (cache, regen ved bot-restart) | `bot/instruments.py` |

## Review-syklus

Plan: månedlig review av `signal_log.json` for hit-rate per
(instrument, horisont, grade) på demo-konto. Loggen bygger seg
opp uavhengig — ingen retention-script trengs i 12.9-vinduet.

Hvis det blir fysisk stort (>100 MB), vurder å rotere ved måneds-
slutt:
```
mv signal_log.json signal_log_$(date +%Y-%m).json
echo "[]" > signal_log.json
```
