"""Bedrock trading bot — cTrader Open API integration.

Port av `~/scalp_edge/trading_bot.py` per Fase 8-plan
(`docs/migration/bot_refactor.md`). Modul-splitt:

- `state`: dataclasses (TradePhase, Candle, TradeState, CandleBuffer)
- `instruments`: instrument-lookup-konstanter (INSTRUMENT_MAP, FX_USD_DIRECTION, osv.)
- `config`: Pydantic-modell for `config/bot.yaml` med startup_only/reloadable split
- `ctrader_client`: Twisted + Protobuf + reconnect (kommer session 41)
- `comms`: signal-server HTTP (kommer session 42)
- `safety`: daily-loss, kill-switch, fetch-fail (kommer session 42)
- `entry`: spot-handlers, filters, confirmation, execute_trade (kommer session 43)
- `sizing`: risk-% → volum (kommer session 43)
- `exit`: P1-P5 exit-prioritet (kommer session 44)
- `__main__`: entry point (kommer session 45)

Gammel `~/scalp_edge/trading_bot.py` kjører uendret i demo-parallell
til Fase 11-12 cutover.
"""
