# SNDK — Telegram Signal Monitor

A conservative, rule-based signal monitor for **SNXX / SNDQ** (daily leveraged/inverse
ETFs tracking the semiconductor complex) that delivers **Arabic** reports to Telegram
on a fixed US-market schedule, with optional on-demand analysis via a Cloudflare
webhook. It never places trades — it watches data, applies a strict entry/exit gate,
and tells you what it sees.

Built to be boring on purpose: every report documents the exact rule that produced
the decision, and market-data problems degrade to **WAIT** with an explicit safety
message instead of a guess.

## How it works

```
        ┌──────────────────────────────────────────────────────────┐
        │  Schedule / webhook                                       │
        │  · GitHub Actions cron (10:30 & 11:15 Riyadh, then        │
        │    every 15 min through US after-hours, weekdays)         │
        │  · Telegram "analyze now" message → Cloudflare worker     │
        └───────────────┬──────────────────────────────────────────┘
                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │  sndk_bot.main.run()                                      │
        │  · skip unless it's a US exchange session (XNYS)          │
        │  · fetch 15-min bars for SNDK, QQQ, SMH (yfinance,        │
        │    with a direct Yahoo chart API fallback)                │
        │  · fetch news: Finviz snapshot + Google News + SEC        │
        │    filings; drop the still-forming candle                 │
        └───────────────┬──────────────────────────────────────────┘
                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │  signals.decide()                                         │
        │  · score = technical (SNDK/QQQ/SMH) + news sentiment      │
        │    + Finviz technical signal                              │
        │  · entry gates: balanced or strong, both need SNDK        │
        │    direction votes, market context and volume             │
        │  · exits need 2 consecutive confirmations (hysteresis)    │
        └───────────────┬──────────────────────────────────────────┘
                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │  report.format_report() → Telegram (Arabic)               │
        │  with position-confirmation buttons; state persisted      │
        │  atomically to data/state.json                            │
        └──────────────────────────────────────────────────────────┘
```

## Signals

| Signal | Meaning |
| --- | --- |
| **SNXX** | Bullish product — confirmed long setup (or keep holding) |
| **SNDQ** | Bearish product — confirmed short setup (or keep holding) |
| **WAIT** | No confirmed entry; hold nothing new |

Every Telegram report also carries three inline buttons so the bot knows your actual
position (`دخلت SNXX` / `دخلت SNDQ` / `لم أدخل`). The bot uses that state to phrase
the next decision as *enter*, *continue*, or *exit* — and never suggests opening a
second position on top of an existing one.

## Decision rules

**Score** (rounded to 3 decimals):

- SNDK technicals: EMA9/EMA21 spread, MACD histogram, 45-minute momentum, RSI zones
- Market context: QQQ (×0.55) and SMH (×0.75) technical components
- News sentiment from recent headlines (clamped to ±0.75)
- Finviz technical snapshot (`top gainer`, `new high`, …) ±0.35

**Risks that dampen confidence**: QQQ and SMH disagree (score ×0.75), weak SNDK
volume (×0.80), no news sources available (technical-only confidence).

**Entry gates** (both require a *completed* 15-minute candle):

- Balanced: |score| ≥ 2.5, SNDK direction votes ≥ 3/4, QQQ or SMH agrees, and
  SNDK volume ≥ 0.8× its 20-bar median.
- Strong: |score| ≥ 3.5, SNDK and SMH components both agree, volume OK.
- Any high-impact headline (earnings, FOMC, CPI, merger, …) within 6 hours blocks
  new entries entirely.

**Exits / hysteresis**: an active signal is held while |score| stays above 1.5;
leaving or reversing requires **2 consecutive runs** with the same decision, so a
single noisy bar cannot flip the bot.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

Requires Python ≥ 3.11. Runtime dependencies are pinned in `pyproject.toml`.

## Configuration

All configuration comes from environment variables (no secrets in files):

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | — | Numeric chat/group/channel id |
| `STATE_PATH` | | `data/state.json` | Where the JSON state file lives |
| `TELEGRAM_WEBHOOK_MODE` | | `false` | `true` = skip long-polling, rely on the webhook |

The remaining runtime parameters (timezone `Asia/Riyadh`, calendar `XNYS`,
thresholds, persistence runs) have conservative defaults in
`src/sndk_bot/config.py` and are deliberately not env-exposed — change them in code
if you understand the trading implications.

## CLI

```
sndk-bot [--version] [--health-check] [--button-test] [--force-report]
         [--position-update {SNXX,SNDQ,EXIT}]
```

| Flag | Description |
| --- | --- |
| `--version` | Print the installed version and exit |
| `--health-check` | Validate the Telegram token and send one connection-test message (no market data) |
| `--button-test` | Send the position buttons for an explicit interaction test |
| `--force-report` | Run a fresh analysis and send the report immediately |
| `--position-update {SNXX,SNDQ,EXIT}` | Persist a confirmed position, then immediately reassess |

## Reporting schedule

GitHub Actions runs the monitor on US trading days (XNYS calendar, weekdays):

| Riyadh time | UTC | Report |
| --- | --- | --- |
| 10:30 | 07:30 | Mandatory — based on the **last completed US session** (no intraday freshness check) |
| 11:15 | 08:15 | Mandatory — intraday, completed candles only |
| every 15 min until 01:45 | 08:15–22:45 | Change alerts only, and only after today's 11:15 report went out |

If market data cannot be fetched or is stale, the bot sends a **safety message**
(WAIT, no directional call) instead of signaling on bad data.

## State persistence

`data/state.json` holds the active/candidate signal, confirmation counts, mandatory
report dates, and your confirmed position. Writes are atomic (temp file + `fsync` +
`os.replace`), so a crash mid-write can never corrupt the file. When running from
GitHub Actions, the workflow commits state changes back automatically
(`chore: persist SNDK bot state`), which is why the file lives in the repo.

## Telegram webhook (optional)

`cloudflare-worker/` is a Cloudflare Worker that converts Telegram messages into
GitHub Actions dispatches:

- **On-demand analysis**: sending `حلل الآن` (or `/analyze`) triggers a
  `force-report` run.
- **Position buttons**: pressing a button stores your position and triggers an
  immediate reassessment (`position-update`).

It verifies every request with `X-Telegram-Bot-Api-Secret-Token`. Required Worker
secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`,
`GITHUB_DISPATCH_TOKEN` (a fine-grained PAT able to dispatch
`sndk-bot.yml` on this repository).

```bash
cd cloudflare-worker
npm install
npx wrangler secret put TELEGRAM_BOT_TOKEN      # ...and the other three
npm run deploy
# Then register the webhook with Telegram:
# https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<SECRET>
```

## Testing

```bash
pytest                       # full suite
pytest --cov=sndk_bot        # coverage (CI requires ≥ 60%)
ruff check src tests
```

CI runs the suite on Python 3.11 and 3.12 with ruff linting and coverage gating.

## Disclaimer

SNXX and SNDQ are daily leveraged/inverse products that reset daily — they are
tactical, short-term instruments, not buy-and-hold. The bot places no trades; all
analysis comes from public data and is **not** investment advice. Always do your
own review before acting.

## License

MIT — see [LICENSE](LICENSE).
