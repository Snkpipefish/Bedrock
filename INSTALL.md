# Installing Bedrock on your own machine

Step-by-step guide to clone Bedrock from GitHub and run it locally
against your own brokerage account.

> ⚠️ **READ FIRST: Scoring and drivers are NOT balanced yet.**
> Bedrock is the author's personal research stack. The 96 drivers and
> their per-family weights in `config/instruments/*.yaml` reflect
> work-in-progress assumptions, not optimised production values.
> Several drivers still return placeholder or near-default scores
> when their underlying data is sparse (e.g. NaturalGas TTF, agri
> disease alerts, ICE COT for retired contracts). Asymmetric
> publish-floors are tuned only for SP500/Nasdaq/Gold/USDJPY/CrudeOil/
> Sugar — every other instrument uses uniform thresholds. Treat all
> live signals as **research output**, not trade recommendations.
> Do not run `--live` until you have validated the system on your
> own data and broker for at least several weeks of demo trading.

---

## 1. Prerequisites

You need:

- **Linux** (Ubuntu 22.04 or similar). Mac/WSL works but is untested.
- **Python 3.12** (the project pins this version; older won't work).
- **Git** + a GitHub account to clone.
- A **cTrader-compatible broker account** (Skilling, IC Markets,
  Pepperstone, FxPro, etc.) with **Open API access enabled**.
- Free API keys (registration required, all free tier):
  - [FRED](https://fred.stlouisfed.org/docs/api/api_key.html) — US macro/yields
  - [USDA NASS QuickStats](https://quickstats.nass.usda.gov/api) — crop progress
  - [EIA Open Data](https://www.eia.gov/opendata/register.php) — US energy
  - [GIE AGSI/ALSI](https://agsi.gie.eu/account) — EU gas storage
  - [USDA FAS](https://api.fas.usda.gov/) — agri exports

Optional but recommended:

- A second account with the same broker for **demo trading** before live.
- `systemd --user` (default on Ubuntu desktop) to run timers.

## 2. Clone the repo

```bash
git clone https://github.com/Snkpipefish/Bedrock.git ~/bedrock
cd ~/bedrock
```

## 3. Install Python toolchain (uv)

[uv](https://docs.astral.sh/uv/) is the package manager Bedrock uses
(pinned dependencies via `uv.lock`).

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync all dependencies (creates .venv/ automatically)
uv sync --all-extras

# Install pre-commit hooks (ruff/yamllint/secret-detection on commit)
uv run pre-commit install
```

Verify the install:

```bash
uv run pytest tests/unit/test_engine_basic.py -q   # should pass
uv run bedrock --help                              # should list CLI commands
```

## 4. Set up secrets

Bedrock reads credentials from `~/.bedrock/secrets.env` (outside the
repo, never committed). Create the file with restrictive permissions:

```bash
mkdir -p ~/.bedrock
cp .env.example ~/.bedrock/secrets.env
chmod 600 ~/.bedrock/secrets.env
$EDITOR ~/.bedrock/secrets.env
```

Fill in your values. The file format is `KEY=VALUE` per line, no
`export ` prefix (systemd `EnvironmentFile=` rejects it). Example:

```ini
FRED_API_KEY=<your-fred-key>
BEDROCK_NASS_API_KEY=<your-nass-key>
BEDROCK_EIA_API_KEY=<your-eia-key>
AGSI_API_KEY=<your-gie-key>
FAS_API_KEY=<your-fas-key>
USDA_API_KEY=<same-as-FAS-or-separate>

# cTrader Open API (see step 5)
CTRADER_CLIENT_ID=<from-openapi.ctrader.com>
CTRADER_CLIENT_SECRET=<same>
CTRADER_ACCESS_TOKEN=<from-OAuth-flow>
CTRADER_REFRESH_TOKEN=<from-OAuth-flow>
CTRADER_ACCOUNT_ID=<your-cTrader-account-id>
```

## 5. Get cTrader Open API credentials

1. Register an Open API application at
   [openapi.ctrader.com](https://openapi.ctrader.com).
2. Note `Client ID` and `Client Secret`.
3. Run the OAuth flow with `scripts/get_token.py`:

   ```bash
   uv run python scripts/get_token.py
   ```

   It prints a URL — open it in a browser, log in to your broker,
   approve, and paste the redirect URL back. The script writes
   `CTRADER_ACCESS_TOKEN` and `CTRADER_REFRESH_TOKEN` for you.
4. Find your account ID via your broker (cTrader desktop → Accounts).
   Use the **demo** account ID first.

## 6. Adjust `INSTRUMENT_MAP` for your broker

This is critical and easy to forget. Bedrock's bot looks up broker
symbols by name from
[`src/bedrock/bot/instruments.py`](src/bedrock/bot/instruments.py)
(`INSTRUMENT_MAP`). The default values are verified against
**Skilling cTrader**. If your broker uses different tickers (e.g.
`Au.SPOT` instead of `XAUUSD`, or `BRENT.CFD` instead of `XBRUSD`),
you must update the candidate lists.

Easy way to discover your broker's symbols:

```bash
# Run the bot once with --demo and check the journal for SYMBOL INFO logs
uv run python -m bedrock.bot --demo &
sleep 30 && pkill -f "bedrock.bot"
```

The bot logs every symbol it finds at startup, plus warnings for any
`INSTRUMENT_MAP` entry that doesn't match. Edit
`INSTRUMENT_MAP` to use your broker's exact ticker as the **first**
candidate per row.

## 7. Backfill historical data

The first time you run, your SQLite DB is empty. Backfill takes
1–2 hours total but each command can be re-run individually if it
fails. Start with the essentials:

```bash
# Prices (Yahoo Finance, no API key needed)
uv run bedrock backfill prices --from 2020-01-01

# CFTC Commitments of Traders (free public CSV)
uv run bedrock backfill cot --from 2020-01-01

# FRED macro series (uses FRED_API_KEY)
uv run bedrock backfill fundamentals --from 2020-01-01

# USDA crop progress (uses BEDROCK_NASS_API_KEY)
uv run bedrock backfill crop-progress --year 2022 --year 2023 --year 2024 --year 2025 --year 2026

# WASDE supply/demand reports
uv run bedrock backfill wasde --from 2020-01-01

# COMEX warehouse inventories
uv run bedrock backfill comex --from 2024-01-01

# EIA energy inventories
uv run bedrock backfill eia-inventories --from 2020-01-01

# ICE COT (Brent/Gasoil/softs)
uv run bedrock backfill cot-ice --from 2024-01-01

# Forex Factory calendar (current week)
uv run bedrock backfill calendar
```

For a full list:

```bash
uv run bedrock backfill --help
```

## 8. Generate signals (without running the bot)

Verify the pipeline works end-to-end before connecting cTrader:

```bash
uv run bedrock signals-all --bot-only --output data/signals_bot.json
```

You should see `Wrote 132 entries from 22/22 instruments to data/signals_bot.json`
(or your subset if you removed instruments). Inspect the file:

```bash
python3 -c "import json; d=json.load(open('data/signals_bot.json')); print(f'{len(d)} entries, {len(set(s[\"instrument\"] for s in d))} instruments')"
```

## 9. Start the local UI

```bash
uv run bedrock server --host 127.0.0.1 --port 5100
```

Open http://127.0.0.1:5100/ in a browser. You should see tabs for
Setups (financial / agri), Skipsloggen (trade log), Kartrommet
(data sources), Drivere (driver registry).

## 10. Run the bot in DEMO mode

> ⚠️ Always test on **demo** account first. Default config uses `--demo`.

Manual one-off run:

```bash
uv run python -m bedrock.bot --demo
```

Watch the logs — you should see authentication, symbol-list reception,
and "INIT" lines for each instrument. If broker symbol matching fails,
fix `INSTRUMENT_MAP` and restart.

## 11. (Optional) Set up systemd timers for unattended operation

Bedrock includes a CLI to generate user-level systemd units from
`config/fetch.yaml`:

```bash
uv run bedrock systemd install
systemctl --user daemon-reload
systemctl --user enable --now bedrock-fetch-prices.timer
systemctl --user enable --now bedrock-fetch-fundamentals.timer
# ... enable each timer you want
systemctl --user list-timers | grep bedrock
```

For the bot itself, an example unit is in `docs/bot_running.md`.

## 12. Run tests before any code changes

```bash
uv run pytest                                # full suite (~2 min, 2814 tests)
uv run pytest -k "instrument or whitelist"   # scoped subset
uv run ruff check . && uv run pyright src/   # lint + type-check
```

---

## What to read next

- `README.md` — high-level overview + architecture
- `LICENSE` — terms of use + trading disclaimer (read it)
- `PLAN.md` — full project roadmap (note: under revision, see README)
- `STATE.md` — session-by-session change history
- `docs/driver_authoring.md` — how to write a new scoring driver
- `docs/rule_authoring.md` — YAML schema for instrument rules
- `docs/decisions/` — Architecture Decision Records (ADR-001..008)
- `docs/bot_running.md` — bot operations + safety mechanisms

---

## Common problems

**`bedrock signals-all` says `Ingen instrumenter funnet`** — you're
running from the wrong directory. `cd ~/bedrock` first.

**Bot logs `[SYMBOL-MAP] X has no match at broker`** — broker uses a
different ticker. Edit `src/bedrock/bot/instruments.py:INSTRUMENT_MAP`
and put the correct ticker first in the candidate list.

**`FredFetchError: HTTP 500`** — FRED's free API has occasional 5xx
hiccups. The runner has retry + tolerance; one failed run is OK.
If failures persist >24h, check FRED status page.

**`Permission denied` on `~/.bedrock/secrets.env`** — set
`chmod 600 ~/.bedrock/secrets.env`.

**`pyright` reports errors after editing** — Bedrock keeps `src/`
at zero pyright errors. Fix before committing.

**Bot rejects all signals as "score below floor"** — your DB is
sparse. Run more backfill steps until coverage report shows
≥80% data presence per instrument.

---

## Reminder

The scoring weights, driver list, and publish-floors in this repo
are tuned for the author's specific risk tolerance, account size,
and broker. **Recalibrate before risking real capital.** A good
starting workflow:

1. Demo for 4+ weeks. Log every signal that fires.
2. Compute per-instrument hit-rate, average return, drawdown, and
   horizon-asymmetry from your demo trade log.
3. Adjust `min_score_publish` floors per (instrument, direction)
   based on your demo data.
4. Re-balance driver weights in instrument YAMLs based on which
   families are actually predictive on your data.
5. Repeat at smaller capital before scaling.

The author makes no claim that the current configuration is
profitable. Treat Bedrock as a framework to encode your own
trading hypotheses, not as a turnkey signal service.
