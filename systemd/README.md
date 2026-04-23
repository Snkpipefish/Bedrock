# Systemd-filer

Timer og service-filer for Bedrock. Installeres én gang på maskinen som kjører
produksjonen.

## Filer

Fylles inn i Fase 11 (cutover):

- `bedrock-main.timer` — hver 4. time (00/04/08/12/16/20 CEST hverdager + lør 00:00)
- `bedrock-main.service` — kjører `uv run bedrock pipeline main`
- `bedrock-hourly.timer` — hver time :40
- `bedrock-hourly.service` — kjører `uv run bedrock pipeline hourly`
- `bedrock-server.service` — alltid-på, kjører Flask på :5000
- `bedrock-bot.service` — alltid-på, kjører cTrader-bot

## Installering

```bash
# Fra repo-roten:
sudo systemctl link /home/pc/bedrock/systemd/bedrock-main.timer
sudo systemctl link /home/pc/bedrock/systemd/bedrock-main.service
# ... gjenta for øvrige

sudo systemctl daemon-reload
sudo systemctl enable --now bedrock-main.timer bedrock-hourly.timer bedrock-server.service bedrock-bot.service
```

## Cutover fra cot-explorer/scalp_edge

Før Bedrock slås på:
1. Skru av gamle timers: `sudo systemctl disable --now cot-explorer.timer cot-prices.timer`
2. Gammel bot lar vi kjøre ferdig åpne trades (se PLAN § 12.2)
3. Når åpne trades er lukket → skru av gammel bot
4. Enable Bedrock-services
