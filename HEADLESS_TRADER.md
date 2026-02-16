# Headless Trader - Lightweight Automated Trading Bot

A minimal, resource-efficient version of the Alpaca Trader that runs 24/7 without a web UI. Perfect for personal use on free hosting tiers.

## Features

- ✅ **No Web UI** - Just a background worker
- ✅ **No Database** - Configuration via YAML files
- ✅ **No Authentication** - Personal use only
- ✅ **Minimal Resources** - Low CPU and memory usage
- ✅ **Easy Configuration** - Simple YAML and .env files
- ✅ **Safe Testing** - Dry-run mode to test without trading
- ✅ **Full Logging** - Monitor activity via logs

## How It Works

1. **Runs on a schedule** (default: every 5 minutes)
2. **Checks your watchlist** for trading signals
3. **Evaluates indicators** (RSI, SMA, MACD, Bollinger Bands)
4. **Executes trades** automatically (when enabled)
5. **Logs everything** for monitoring

---

## Quick Start

### 1. Setup Environment

Copy the example environment file:
```bash
cp .env.headless .env
```

Edit `.env` with your credentials:
```bash
# Required
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here

# Paper trading (true) or live trading (false)
ALPACA_PAPER=true

# Enable/disable trade execution
TRADING_ENABLED=false  # Start with false to test!
```

### 2. Configure Watchlist

Edit `config/watchlist.yaml`:
```yaml
watchlist:
  - symbol: AAPL
    name: Apple Inc.
  - symbol: MSFT
    name: Microsoft Corporation
  - symbol: GOOGL
    name: Alphabet Inc.
```

### 3. Configure Settings

Edit `config/settings.yaml` to adjust:
- Indicator periods (RSI, SMA, MACD, Bollinger)
- Signal aggregation mode
- Execution parameters (order type, position size, etc.)
- Schedule interval

### 4. Run Locally (Test First!)

```bash
python headless_trader.py
```

You'll see logs like:
```
2026-02-16 15:30:00 - INFO - Checking signals at 2026-02-16 15:30:00
2026-02-16 15:30:02 - INFO - AAPL: BUY (strength: 75.0%) - {'rsi_signal': 'buy', 'sma_signal': 'buy'}
2026-02-16 15:30:02 - INFO - 🔵 BUY signal for AAPL (trading disabled)
2026-02-16 15:30:05 - INFO - Summary: 3 signals checked, 1 BUY, 0 SELL, 0 trades executed
```

### 5. Enable Trading (When Ready)

Once you've tested and verified signals look correct:

```bash
# In .env file, change:
TRADING_ENABLED=true
```

Restart the bot and it will execute real trades!

---

## Deployment to Render (Free Tier)

### Option 1: Background Worker

1. **Create `render_worker.yaml`:**

```yaml
services:
  - type: worker
    name: alpaca-trader-worker
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python headless_trader.py
    envVars:
      - key: ALPACA_API_KEY
        sync: false
      - key: ALPACA_SECRET_KEY
        sync: false
      - key: ALPACA_PAPER
        value: true
      - key: TRADING_ENABLED
        value: false
      - key: PYTHON_VERSION
        value: 3.11.0
```

2. **Push to GitHub**
3. **Deploy on Render:**
   - New → Background Worker
   - Connect repository
   - It will auto-detect `render_worker.yaml`
   - Add your API keys in environment variables
   - Deploy!

### Option 2: Cron Job (Even Lighter)

Use Render's Cron Jobs (runs periodically, uses zero resources between runs):

```yaml
services:
  - type: cron
    name: alpaca-trader-cron
    env: python
    schedule: "*/5 * * * *"  # Every 5 minutes
    buildCommand: pip install -r requirements.txt
    startCommand: python headless_trader.py
```

---

## Configuration Reference

### Watchlist (`config/watchlist.yaml`)

Simple list of stocks to monitor:
```yaml
watchlist:
  - symbol: AAPL
    name: Apple Inc.
  - symbol: TSLA
    name: Tesla Inc.
  # Add more stocks here
```

### Settings (`config/settings.yaml`)

Already configured with sensible defaults. Key sections:

**Schedule:**
```yaml
schedule:
  enabled: true
  interval_minutes: 5  # How often to check
  market_hours_only: true  # Only trade during market hours
```

**Execution:**
```yaml
execution:
  order_type: market
  position_size_pct: 10  # Use 10% of capital per position
  max_positions: 5  # Max 5 open positions
```

---

## Monitoring

### View Logs

**Locally:**
```bash
tail -f headless_trader.log
```

**On Render:**
- Dashboard → Your service → Logs tab
- See real-time activity

### Log Format

```
2026-02-16 15:30:00 - INFO - Checking signals...
2026-02-16 15:30:02 - INFO - AAPL: BUY (strength: 75.0%)
2026-02-16 15:30:02 - INFO - ✅ BUY order placed for AAPL
```

---

## Safety Features

1. **Dry-run mode**: Set `TRADING_ENABLED=false` to test without executing trades
2. **Paper trading**: Set `ALPACA_PAPER=true` to trade with fake money
3. **Market hours check**: Only trades during market hours (optional)
4. **Position limits**: Maximum number of open positions
5. **Position sizing**: Risk management via % of capital
6. **Graceful shutdown**: Handles Ctrl+C and SIGTERM properly

---

## Resource Usage

**Background Worker (24/7):**
- CPU: ~5-10% on free tier
- Memory: ~100-150MB
- Perfect for Render free tier!

**Cron Job:**
- CPU: Only during runs (~30 seconds every 5 minutes)
- Memory: Zero between runs
- Even better for minimizing resource usage!

---

## Troubleshooting

**"No API keys found"**
- Make sure `.env` file exists and has `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`

**"Watchlist is empty"**
- Check that `config/watchlist.yaml` exists and has symbols listed

**"All signals are HOLD"**
- Normal! Markets don't always have clear signals
- Check your indicator settings if you never see BUY/SELL
- Verify lookback_days is sufficient (recommended: 100+)

**"N/A indicators"**
- Increase `lookback_days` in settings.yaml (need enough historical data)
- Use `1Day` timeframe for most reliable signals

---

## Comparison: Headless vs Full Dashboard

| Feature | Headless | Full Dashboard |
|---------|----------|----------------|
| **Web UI** | ❌ No | ✅ Yes |
| **Authentication** | ❌ No | ✅ Yes |
| **Database** | ❌ No (YAML files) | ✅ PostgreSQL |
| **Multi-user** | ❌ No | ✅ Yes |
| **Resource usage** | ✅ Very low | ⚠️ Higher |
| **Setup complexity** | ✅ Simple | ⚠️ Complex |
| **Deployment cost** | ✅ Free tier OK | ⚠️ Needs paid tier |
| **Configuration** | ✅ YAML files | ⚠️ Database + UI |
| **Monitoring** | Logs only | Web UI + logs |

---

## Switching Between Modes

You can run **both** if needed:

- **Headless** on Render (24/7 automated trading)
- **Dashboard** locally (when you want to monitor with UI)

Both use the same codebase, just different entry points!

---

## Next Steps

1. ✅ Test locally with `TRADING_ENABLED=false`
2. ✅ Verify signals look correct
3. ✅ Test with paper trading (`ALPACA_PAPER=true`)
4. ✅ Deploy to Render as background worker
5. ✅ Monitor for a few days
6. ✅ Enable live trading when confident

Happy trading! 🚀
