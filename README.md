# Alpaca Trader

A Python-based automated trading bot that uses technical indicators to generate buy/sell signals and execute trades through the [Alpaca API](https://alpaca.markets/). Supports both **stocks and crypto**, with a secure multi-user web dashboard, automated background scheduling, and a CLI for power users.

## Features

- **Multiple Technical Indicators**
  - RSI (Relative Strength Index)
  - SMA Crossover (Simple Moving Average)
  - MACD (Moving Average Convergence Divergence)
  - Bollinger Bands

- **Flexible Signal Aggregation**
  - Unanimous: All indicators must agree
  - Majority: Configurable minimum number of indicators must agree
  - Any: At least one indicator triggers a signal

- **Multiple Operating Modes**
  - **Scan**: Read-only signal analysis
  - **Trade**: Execute trades based on signals
  - **Schedule**: Automated trading on a timer
  - **Backtest**: Historical signal analysis
  - **Dashboard**: Basic web UI for monitoring and control
  - **Dashboard-Secure**: Production-ready web UI with authentication
  - **Status**: Account and portfolio summary

- **Stocks and Crypto**
  - Stocks routed to Alpaca's stock data and trading APIs
  - Crypto pairs (e.g. `BTC/USD`) routed to crypto APIs automatically
  - Crypto trading bypasses market-hours check (24/7)
  - Crypto uses GTC time-in-force (DAY not supported by Alpaca for crypto)

- **Risk Management**
  - Configurable position sizing (percentage of portfolio)
  - Maximum position limits
  - Dry-run mode for testing
  - Paper trading support

- **Secure Web Dashboard**
  - Multi-user authentication with role-based access (admin/viewer)
  - Optional two-factor authentication (TOTP)
  - Encrypted API key storage per user
  - Password reset via email
  - Real-time portfolio monitoring
  - Signal visualization and price analysis panel
  - Position tracking and trade history

## Installation

### Prerequisites

- Python 3.8 or higher
- Alpaca API account (paper trading or live)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/jcap24/alpaca-trader.git
   cd alpaca-trader
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure API credentials:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your Alpaca API credentials:
   ```env
   ALPACA_API_KEY=your_api_key_here
   ALPACA_SECRET_KEY=your_secret_key_here
   ```

## Configuration

### Settings (`config/settings.yaml`)

Configure technical indicators, signal aggregation, execution parameters, and scheduling:

```yaml
indicators:
  rsi:
    enabled: true
    period: 14
    overbought: 70
    oversold: 30

  sma_crossover:
    enabled: true
    short_period: 20
    long_period: 50

  macd:
    enabled: true
    fast_period: 12
    slow_period: 26
    signal_period: 9

  bollinger_bands:
    enabled: true
    period: 20
    std_dev: 2.0

signal:
  mode: "majority"        # "majority", "unanimous", or "any"
  min_agree: 2           # Minimum indicators that must agree (majority mode)

execution:
  order_type: "market"
  time_in_force: "day"
  position_size_pct: 5.0  # Percent of portfolio per trade
  max_positions: 10
  allow_short: false

data:
  timeframe: "1Day"       # "1Min", "5Min", "15Min", "1Hour", "1Day"
  lookback_days: 100

schedule:
  enabled: true
  interval_minutes: 60
  market_hours_only: true
```

### Watchlist (`config/watchlist.yaml`)

Define the stocks to monitor:

```yaml
watchlist:
  - symbol: AAPL
    name: Apple Inc.
  - symbol: MSFT
    name: Microsoft Corp.
  # Add more symbols...
```

## Usage

### Command Line Interface

#### Scan for Signals (Read-Only)

```bash
python -m alpaca_trader.main scan
```

Scan a specific symbol:
```bash
python -m alpaca_trader.main scan --symbol AAPL
```

#### Execute Trades

```bash
python -m alpaca_trader.main trade
```

Dry-run mode (no actual orders):
```bash
python -m alpaca_trader.main trade --dry-run
```

Trade a specific symbol:
```bash
python -m alpaca_trader.main trade --symbol AAPL
```

#### Scheduled Trading

Run automated trading on a schedule:
```bash
python -m alpaca_trader.main schedule
```

Schedule mode with dry-run:
```bash
python -m alpaca_trader.main schedule --dry-run
```

#### Portfolio Status

View account summary and positions:
```bash
python -m alpaca_trader.main status
```

#### Backtesting

Run signals against historical data:
```bash
python -m alpaca_trader.main backtest --days 30
```

Backtest a specific symbol:
```bash
python -m alpaca_trader.main backtest --days 30 --symbol AAPL
```

#### Web Dashboard (Basic)

Start the basic web interface:
```bash
python -m alpaca_trader.main dashboard
```

With custom host/port:
```bash
python -m alpaca_trader.main dashboard --host 0.0.0.0 --port 8080
```

Dashboard without scheduler:
```bash
python -m alpaca_trader.main dashboard --no-scheduler
```

#### Web Dashboard (Secure — Recommended for Production)

The secure dashboard adds multi-user authentication, 2FA, encrypted API key storage, password reset via email, and a price analysis panel. This is the version deployed on Render.

Required environment variables:
```env
ENCRYPTION_KEY=<fernet-key>        # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SECRET_KEY=<flask-secret>          # Any long random string
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<initial-password>
```

Start the secure dashboard:
```bash
python -m alpaca_trader.main dashboard-secure
```

With custom host/port:
```bash
python -m alpaca_trader.main dashboard-secure --host 0.0.0.0 --port 8080
```

The admin account is created automatically on first run if no users exist. Log in at `http://localhost:8000` and add your Alpaca API credentials through the Settings page.

> **Note**: `ENCRYPTION_KEY` must never change after users have saved their API keys — changing it will make all stored keys unreadable.

### Logging

Set log level with `--log-level`:
```bash
python -m alpaca_trader.main scan --log-level DEBUG
```

Available levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Signal Logic

The trading system uses a **3-stage process** to generate trading decisions:

1. **Calculate Technical Indicators** → Generate individual signals
2. **Aggregate Signals** → Combine multiple indicator signals
3. **Execute Action** → BUY, SELL, or HOLD

### Technical Indicators

Each enabled indicator independently analyzes price data and generates buy/sell signals:

#### RSI (Relative Strength Index)
Measures momentum by comparing recent gains to recent losses.

- **Buy Signal**: RSI < 30 (oversold - stock may be undervalued)
- **Sell Signal**: RSI > 70 (overbought - stock may be overvalued)
- **Hold**: RSI between 30-70 (neutral zone)

**Example**: RSI = 25 → "buy" signal

#### SMA Crossover (Simple Moving Average)
Detects trend changes by comparing short-term vs long-term averages.

- **Buy Signal**: Short SMA (20-day) crosses **above** Long SMA (50-day) - "Golden Cross"
- **Sell Signal**: Short SMA crosses **below** Long SMA - "Death Cross"
- **Hold**: No crossover detected

**Crossover Detection Logic**:
- Current: `short_sma > long_sma`
- Previous: `short_sma <= long_sma`
- Both conditions true → Upward crossover → BUY

**Example**:
- Yesterday: SMA(20)=150, SMA(50)=152
- Today: SMA(20)=153, SMA(50)=152
- Result: "buy" signal (golden cross)

#### MACD (Moving Average Convergence Divergence)
Shows momentum changes through the relationship between two moving averages.

- **Buy Signal**: MACD line crosses **above** signal line
- **Sell Signal**: MACD line crosses **below** signal line
- **Hold**: No crossover

Uses same crossover logic as SMA with periods: Fast=12, Slow=26, Signal=9

#### Bollinger Bands
Identifies overbought/oversold conditions using volatility bands.

- **Buy Signal**: Price touches or drops **below** lower band (potential bounce)
- **Sell Signal**: Price touches or rises **above** upper band (potential reversal)
- **Hold**: Price between bands

**Bands**: Middle (20-day SMA) ± (2 × standard deviation)

**Example**: Close=$95, Lower Band=$96 → "buy" signal

### Signal Aggregation

After all indicators generate their signals, the system aggregates them based on the configured `signal.mode`:

#### Mode: "majority" (Default)
```yaml
signal:
  mode: "majority"
  min_agree: 2
```

**Logic**: At least `min_agree` indicators must agree, and that side must have more votes.

**Example**:
- RSI: "buy"
- SMA: "buy"
- MACD: "sell"
- Bollinger: None

Result: 2 buy vs 1 sell → **BUY** (majority wins, min_agree=2 met)

#### Mode: "unanimous"
```yaml
signal:
  mode: "unanimous"
```

**Logic**: ALL enabled indicators must agree. Very conservative.

**Example**:
- All 4 say "buy" → **BUY**
- 3 say "buy", 1 says "sell" → **HOLD** (not unanimous)

#### Mode: "any"
```yaml
signal:
  mode: "any"
```

**Logic**: Any single indicator can trigger a trade, but only if there's no conflict.

**Example**:
- RSI: "buy", others: None → **BUY**
- RSI: "buy", MACD: "sell" → **HOLD** (conflicting signals)

### Signal Strength

The system calculates signal strength as:

```
strength = max(buy_count, sell_count) / total_enabled_indicators
```

**Example**: 3 out of 4 indicators agree → strength = 75%

This is logged for transparency and could be used to filter weak signals or adjust position sizes.

### Complete Example Walkthrough

**Scanning AAPL with majority mode (min_agree=2):**

**Step 1: Calculate Indicators**
```
RSI = 28           → "buy" (oversold)
SMA: 155 > 152     → "buy" (crossed up yesterday)
MACD: crossed up   → "buy"
Bollinger: $154    → None (between bands)
```

**Step 2: Count Votes**
```
buy_count = 3
sell_count = 0
total_enabled = 4
```

**Step 3: Apply Aggregation**
```
buy_count (3) >= min_agree (2) ✓
buy_count (3) > sell_count (0) ✓
→ Action = BUY
```

**Step 4: Calculate Strength**
```
strength = 3 / 4 = 0.75 (75%)
```

**Output**:
```
[+] AAPL: BUY (strength=75%) | {'rsi_signal': 'buy', 'sma_signal': 'buy',
                                 'macd_signal': 'buy', 'bb_signal': None}
```

### Key Principles

- Each indicator is **independent** (calculates based only on price data)
- **Crossover indicators** (SMA, MACD) only signal at the crossover moment
- **Threshold indicators** (RSI, Bollinger) signal whenever conditions are met
- **Conflicting signals default to HOLD** (safety mechanism)
- Signal mode controls strategy aggressiveness:
  - `unanimous`: Very conservative
  - `majority`: Balanced (recommended)
  - `any`: Aggressive

## Project Structure

```
alpaca-trader/
├── alpaca_trader/
│   ├── __init__.py
│   ├── auto_trader.py        # Per-user trading logic (called by scheduler)
│   ├── client.py             # Alpaca API client wrapper (stocks + crypto)
│   ├── config.py             # Configuration loading (YAML + DB settings)
│   ├── dashboard.py          # Basic Flask dashboard (CLI only)
│   ├── dashboard_secure.py   # Production Flask app with auth (Render)
│   ├── data.py               # Market data fetching (stocks + crypto)
│   ├── executor.py           # Order execution logic with safety guards
│   ├── indicators.py         # Technical indicator calculations
│   ├── logger.py             # Logging setup
│   ├── main.py               # CLI entry point
│   ├── models.py             # SQLAlchemy models (User, UserSettings, etc.)
│   ├── portfolio.py          # Portfolio management
│   ├── scheduler.py          # APScheduler background trading scheduler
│   ├── security.py           # Fernet encryption for API keys, password hashing
│   └── signals.py            # Signal aggregation logic
├── config/
│   ├── settings.yaml         # Default trading configuration
│   └── watchlist.yaml        # Default stock/crypto watchlist
├── scripts/
│   └── auto_init.py          # DB init + admin user creation (Render release cmd)
├── templates/                # Jinja2 HTML templates for the dashboard
├── tests/                    # Test suite
├── wsgi.py                   # Gunicorn entry point (imports dashboard_secure)
├── Procfile                  # Render process definitions
├── .env.example              # Environment variables template
├── .gitignore
├── requirements.txt
├── DEVELOPER.md              # Architecture guide for contributors
└── README.md
```

## Safety Features

- **Paper Trading**: Uses Alpaca paper trading by default
- **Dry-Run Mode**: Test strategies without executing real orders
- **Position Limits**: Configurable maximum number of positions
- **Position Sizing**: Risk-controlled position sizing as percentage of portfolio
- **Market Hours**: Optional restriction to market hours only

## Development

### Running Tests

```bash
pytest
```

### Dependencies

Key dependencies include:
- `alpaca-py` - Alpaca API client
- `pandas` - Data manipulation
- `ta` - Technical analysis library
- `flask` - Web dashboard
- `flask-login` - Session-based authentication
- `flask-sqlalchemy` - Database ORM
- `flask-wtf` - CSRF protection
- `flask-mail` - Password reset emails
- `cryptography` - Fernet encryption for stored API keys
- `apscheduler` - Job scheduling
- `pyyaml` - Configuration files
- `pyotp` - TOTP two-factor authentication
- `gunicorn` - WSGI server for production

## Warning

This software is for educational purposes. **Use at your own risk.** Always test thoroughly in paper trading mode before considering any live trading. Past performance does not guarantee future results.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/jcap24/alpaca-trader/issues).
