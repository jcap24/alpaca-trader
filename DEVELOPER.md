# Developer Guide

This document explains how the backend modules connect to each other and to the frontend, and how to add new features.

---

## Architecture Overview

```
Browser (dashboard.html)
        │
        │  fetch('/api/...')
        ▼
Flask routes (dashboard_secure.py)
        │
        ├── security.py      ← decrypt API keys before every request
        ├── signals.py       ← evaluate BUY/SELL/HOLD from indicator data
        ├── executor.py      ← translate signals into Alpaca orders
        └── auto_trader.py   ← background scheduler (calls signals + executor every 5 min)
                │
                └── scheduler.py  ← lower-level APScheduler wrapper (used in CLI mode)
```

There is no separate frontend build step. `dashboard.html` is a single HTML file served directly by Flask. All communication between the page and the server happens via `fetch()` calls to REST API endpoints defined in `dashboard_secure.py`.

---

## File Roles

### `dashboard_secure.py` — The Hub

This is the only file that defines Flask routes. Every button click or data load in the UI maps to a route here.

- `create_app()` initializes Flask, the database, extensions, and starts `AutoTrader`.
- `get_user_client()` is a helper called at the top of most routes. It loads the user's **active account** from the DB, decrypts the API keys using `security.py`, and returns an `AlpacaClient`.
- All routes under `/api/` are the contract between the frontend and backend.

### `security.py` — Encryption & Auth Utilities

Three classes, each with a single responsibility:

| Class | What it does |
|---|---|
| `EncryptionManager` | Encrypts/decrypts Alpaca API keys stored in the DB using Fernet symmetric encryption. Initialized once in `create_app()` using the `ENCRYPTION_KEY` env var. |
| `PasswordManager` | Hashes and verifies user passwords (pbkdf2:sha256 via Werkzeug). |
| `TwoFactorAuth` | Generates TOTP secrets, QR codes, and verifies 6-digit codes. |

**How it connects to the frontend:**
`security.py` is never called directly from frontend requests. Instead, `get_user_client()` in `dashboard_secure.py` calls `_encryption_manager.decrypt(...)` before building an `AlpacaClient` — this happens transparently on every API route that needs to talk to Alpaca.

The 2FA flow (`TwoFactorAuth`) is triggered by these routes:
```
POST /api/2fa/setup    → generates secret, saves to User model
GET  /api/2fa/qrcode   → returns QR code PNG
POST /api/2fa/enable   → verifies token then sets is_2fa_enabled = True
POST /api/2fa/disable  → disables 2FA
```

### `signals.py` — Signal Logic

Contains two things:

1. `Action` enum: `BUY`, `SELL`, `HOLD`
2. `evaluate_signals(df, symbol, settings) → Signal`

`evaluate_signals` reads the last row of a DataFrame that already has indicator columns computed (e.g. `rsi_signal`, `sma_signal`, `macd_signal`, `bb_signal`), counts votes, and applies the user's configured aggregation mode (`unanimous`, `majority`, or `any`).

**How it connects to the frontend:**
The `/api/signals` route in `dashboard_secure.py` orchestrates the full pipeline:

```
GET /api/signals
  → fetch_bars(client, symbols, ...)    # pulls OHLCV from Alpaca
  → compute_all(df, settings)           # indicators.py adds signal columns
  → evaluate_signals(df, symbol, ...)   # signals.py votes on BUY/SELL/HOLD
  → returns JSON list to dashboard.html
```

The dashboard renders these as colored badges (BUY/SELL/HOLD) in the Live Signals panel.

### `executor.py` — Order Execution

`OrderExecutor.execute_signal(signal, dry_run=False)` takes a `Signal` and submits a market order to Alpaca, with safety guards:

- Won't BUY if already in a position
- Won't BUY if `max_positions` is reached
- Won't SELL short unless `allow_short` is enabled
- Calculates order size as `equity × position_size_pct / 100`

**How it connects to the frontend:**
`executor.py` is **not called directly from any HTTP route**. It is only called from:
1. `auto_trader.py` — during the background trading cycle
2. `main.py` — when running the bot from the CLI

The `/api/execution` routes only read/write the execution *settings* (order type, position size, etc.) from the database. The actual execution happens in the background via `AutoTrader`.

### `scheduler.py` — CLI Scheduler (Blocking/Background)

A thin wrapper around APScheduler used when running the bot from the **command line** (`python -m alpaca_trader`). It accepts a `run_fn` callable and fires it on an interval or cron schedule.

**This file is not used by the dashboard.** The dashboard uses `auto_trader.py` instead.

### `auto_trader.py` — Dashboard Background Scheduler

This is the scheduler that actually runs inside the Flask app. It starts when `create_app()` is called and runs a background job every 5 minutes.

Each cycle:
1. Queries all users with `schedule_enabled = True`
2. For each user: decrypts their API keys, loads their watchlist and settings
3. Calls `fetch_bars` → `compute_all` → `evaluate_signals` → `executor.execute_signal`
4. Writes audit log entries for every trade

**How it connects to the frontend:**
The user toggles automated trading on/off via the dashboard, which calls:
```
PUT /api/indicators   → saves schedule_enabled to the Settings DB model
```
On the next 5-minute tick, `AutoTrader._check_all_users()` picks up the change automatically.

The `/api/scheduler-status` route lets the dashboard show the running/stopped badge in the header.

---

## Data Flow: From Click to Trade

Here is the full path for a manual signal check (user clicks "Refresh Signals"):

```
dashboard.html
  fetch('/api/signals')
      │
dashboard_secure.py → api_signals()
      │
      ├── Watchlist.query (DB)          → get user's symbols
      ├── SettingsModel.query (DB)       → get indicator config
      ├── get_user_client()
      │     └── security.py             → decrypt API keys
      │
      ├── fetch_bars(client, symbols)   → Alpaca market data API
      ├── indicators.compute_all(df)    → adds rsi_signal, sma_signal, etc.
      └── signals.evaluate_signals(df)  → returns BUY/SELL/HOLD
      │
      └── jsonify([{symbol, action, strength, details, price}])
      │
dashboard.html renders signal badges
```

Here is the full path for automated trading:

```
AutoTrader._check_all_users() [every 5 min, background thread]
      │
      ├── DB query: users with schedule_enabled=True
      └── for each user:
            ├── security.py → decrypt API keys
            ├── fetch_bars → Alpaca
            ├── compute_all → indicators.py
            ├── evaluate_signals → signals.py
            └── executor.execute_signal → Alpaca orders API
                  └── audit_log written to DB
```

---

## Adding a New Indicator

To add a new indicator (e.g. Stochastic RSI), touch these files in order:

**1. `indicators.py`** — add the compute function:
```python
def compute_stoch_rsi(df: pd.DataFrame, config: StochRSIConfig) -> pd.DataFrame:
    # ... compute values ...
    df["stoch_rsi_signal"] = None
    df.loc[df["stoch_rsi"] < 20, "stoch_rsi_signal"] = "buy"
    df.loc[df["stoch_rsi"] > 80, "stoch_rsi_signal"] = "sell"
    return df
```
Then register it in `compute_all()`:
```python
if settings.stoch_rsi.enabled:
    df = compute_stoch_rsi(df, settings.stoch_rsi)
```

**2. `config.py`** — add a config dataclass and add it to `Settings`:
```python
@dataclass
class StochRSIConfig:
    enabled: bool
    period: int

@dataclass
class Settings:
    ...
    stoch_rsi: StochRSIConfig
```

**3. `signals.py`** — register the new signal column in `evaluate_signals()`:
```python
if settings.stoch_rsi.enabled:
    signal_columns.append("stoch_rsi_signal")
```

**4. `models.py`** — add columns to the `Settings` DB model:
```python
stoch_rsi_enabled = db.Column(db.Boolean, default=True, nullable=False)
stoch_rsi_period  = db.Column(db.Integer, default=14, nullable=False)
```
Then run a DB migration or let `db.create_all()` pick it up on restart.

**5. `dashboard_secure.py`** — expose the new settings in the `/api/indicators` GET and PUT routes, and wire it into the `Settings` dataclass construction (there are two places: `api_signals()` and `AutoTrader._create_settings_object()`).

**6. `dashboard.html`** — add a toggle/input in the Indicators panel, and include the new fields in the `PUT /api/indicators` payload.

---

## Adding a New API Endpoint

All routes live inside the `create_app()` function in `dashboard_secure.py`. To add a new route:

```python
@app.route("/api/my-feature", methods=["GET"])
@login_required
def my_feature():
    # current_user is available from Flask-Login
    client = get_user_client()   # decrypts keys, returns AlpacaClient
    # ... your logic ...
    return jsonify({"result": "..."})
```

Then call it from `dashboard.html`:
```javascript
const resp = await fetch('/api/my-feature');
const data = await resp.json();
```

For write endpoints (`POST`, `PUT`, `DELETE`) add `@csrf.exempt` since the dashboard uses JSON fetch, not HTML forms, and include `methods=["POST"]` in the decorator.

---

## Adding a New Execution Guard

Guards live in `executor.py` inside `OrderExecutor.execute_signal()`. They all follow the same pattern — check a condition, log a reason, return `None` to skip:

```python
# Example: don't trade on Fridays
from datetime import datetime
if datetime.today().weekday() == 4:  # Friday
    logger.info("Skipping %s: no trading on Fridays", signal.symbol)
    return None
```

Any new guard parameters should be added to `ExecutionConfig` in `config.py` and the `Settings` DB model in `models.py`.

---

## Key Conventions

- **All settings are per-user**, stored in the `settings` DB table. There is one row per user.
- **API keys are always encrypted** at rest. Never store them as plaintext. Always go through `EncryptionManager.encrypt/decrypt`.
- **`ENCRYPTION_KEY` must never change** after first deployment — changing it makes all stored API keys unreadable.
- **DB migrations**: the app uses Flask-Migrate. After adding a model column run `flask db migrate` and `flask db upgrade`. On Render the `release` command in the Procfile handles this automatically via `scripts/auto_init.py`.
- **Audit logging**: call `log_audit(action, resource_type, resource_id, details)` for any significant user action. This writes to the `audit_logs` table.
- **Rate limiting**: sensitive routes have `@limiter.limit(...)`. Add this to any new endpoint that accepts user input.
