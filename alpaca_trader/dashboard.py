import logging
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import (
    load_api_keys, load_settings, load_watchlist,
    load_accounts, save_accounts, add_account, update_account,
    delete_account, set_active_account, get_active_account
)
from alpaca_trader.data import fetch_bars
from alpaca_trader.indicators import compute_all
from alpaca_trader.logger import setup_logger
from alpaca_trader.portfolio import PortfolioManager
from alpaca_trader.scheduler import TradingScheduler
from alpaca_trader.signals import evaluate_signals
from alpaca_trader.main import run_scan

logger = logging.getLogger("alpaca_trader")

# Module-level references set by start_dashboard()
_client: AlpacaClient = None
_settings = None
_watchlist: list[str] = None
_watchlist_raw: list[dict] = None
_pm: PortfolioManager = None
_scheduler: TradingScheduler = None
_watchlist_path: Path = None
_settings_path: Path = None


def save_watchlist_to_file(watchlist_path: Path, entries: list[dict]) -> None:
    """Save watchlist entries to YAML file."""
    watchlist_data = {"watchlist": entries}
    with open(watchlist_path, "w") as f:
        yaml.dump(watchlist_data, f, default_flow_style=False)
    logger.info("Watchlist saved with %d entries", len(entries))


def reload_watchlist(watchlist_path: Path) -> None:
    """Reload watchlist from file into memory."""
    global _watchlist, _watchlist_raw
    _watchlist = load_watchlist(watchlist_path)
    with open(watchlist_path, "r") as f:
        raw = yaml.safe_load(f)
    _watchlist_raw = raw["watchlist"]
    logger.info("Watchlist reloaded: %d symbols", len(_watchlist))


def save_settings_to_file(settings_path: Path, settings_dict: dict) -> None:
    """Save settings to YAML file."""
    with open(settings_path, "w") as f:
        yaml.dump(settings_dict, f, default_flow_style=False)
    logger.info("Settings saved to file")


def reload_settings(settings_path: Path) -> None:
    """Reload settings from file into memory."""
    global _settings
    _settings = load_settings(settings_path)
    logger.info("Settings reloaded from file")


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent / "templates"),
        static_folder=str(Path(__file__).parent.parent / "static"),
    )

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    @app.route("/api/account")
    def api_account():
        summary = _pm.get_summary()
        summary["market_open"] = _pm.is_market_open()
        return jsonify(summary)

    @app.route("/api/positions")
    def api_positions():
        positions = _pm.get_positions_summary()
        return jsonify(positions)

    @app.route("/api/orders")
    def api_orders():
        order_filter = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=50,
        )
        orders = _client.get_orders(filter=order_filter)
        result = []
        for o in orders:
            result.append({
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value if o.side else None,
                "qty": str(o.qty) if o.qty else None,
                "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
                "status": str(o.status.value) if o.status else str(o.status),
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
                "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
                "type": str(o.type.value) if o.type else None,
            })
        return jsonify(result)

    @app.route("/api/signals")
    def api_signals():
        bars = fetch_bars(
            _client, _watchlist, _settings.data.timeframe, _settings.data.lookback_days
        )
        results = []
        for symbol, df in bars.items():
            df = compute_all(df, _settings)
            signal = evaluate_signals(df, symbol, _settings)

            name = symbol
            for entry in _watchlist_raw:
                if entry["symbol"] == symbol:
                    name = entry.get("name", symbol)
                    break

            results.append({
                "symbol": signal.symbol,
                "name": name,
                "action": signal.action.value,
                "strength": round(signal.strength * 100, 1),
                "details": signal.details,
                "price": float(df["close"].iloc[-1]) if not df.empty else None,
            })
        return jsonify(results)

    @app.route("/api/portfolio-history")
    def api_portfolio_history():
        period = request.args.get("period", "1M")
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest
            history_req = GetPortfolioHistoryRequest(
                period=period,
                timeframe="1D",
            )
            history = _client.get_portfolio_history(filter=history_req)
            return jsonify({
                "timestamp": history.timestamp,
                "equity": history.equity,
                "profit_loss": history.profit_loss,
                "profit_loss_pct": history.profit_loss_pct,
                "base_value": history.base_value,
            })
        except Exception as e:
            logger.warning("Portfolio history unavailable: %s", e)
            return jsonify({
                "timestamp": [],
                "equity": [],
                "profit_loss": [],
                "profit_loss_pct": [],
                "base_value": 0,
            })

    @app.route("/api/watchlist")
    def api_watchlist():
        return jsonify(_watchlist_raw)

    @app.route("/api/watchlist", methods=["POST"])
    def add_watchlist_symbol():
        """Add a new symbol to the watchlist."""
        try:
            data = request.get_json()
            symbol = data.get("symbol", "").strip().upper()

            # Validate symbol format (1-5 uppercase letters)
            if not symbol or not symbol.isalpha() or len(symbol) > 5:
                return jsonify({"error": "Symbol must be 1-5 letters"}), 400

            # Check for duplicates
            if any(e["symbol"] == symbol for e in _watchlist_raw):
                return jsonify({"error": f"Symbol {symbol} already exists"}), 409

            # Validate ticker with Alpaca API and get company name
            asset = _client.get_asset(symbol)
            if asset is None:
                return jsonify({"error": f"Symbol {symbol} not found. Please verify it's a valid ticker."}), 404

            # Use the official asset name from Alpaca
            name = asset.name if hasattr(asset, 'name') and asset.name else symbol

            # Add to list
            _watchlist_raw.append({"symbol": symbol, "name": name})

            # Save to file
            save_watchlist_to_file(_watchlist_path, _watchlist_raw)

            # Reload in memory
            reload_watchlist(_watchlist_path)

            logger.info("Added %s (%s) to watchlist", symbol, name)
            return jsonify({"success": True, "symbol": symbol, "name": name}), 201

        except Exception as e:
            logger.exception("Failed to add symbol: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/watchlist/<symbol>", methods=["DELETE"])
    def remove_watchlist_symbol(symbol: str):
        """Remove a symbol from the watchlist."""
        try:
            symbol = symbol.upper()

            # Filter out the symbol
            original_count = len(_watchlist_raw)
            filtered = [e for e in _watchlist_raw if e["symbol"] != symbol]

            if len(filtered) == original_count:
                return jsonify({"error": f"Symbol {symbol} not found"}), 404

            # Update global variable
            _watchlist_raw.clear()
            _watchlist_raw.extend(filtered)

            # Save to file
            save_watchlist_to_file(_watchlist_path, _watchlist_raw)

            # Reload in memory
            reload_watchlist(_watchlist_path)

            logger.info("Removed %s from watchlist", symbol)
            return jsonify({"success": True, "symbol": symbol}), 200

        except Exception as e:
            logger.exception("Failed to remove symbol: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/indicators")
    def get_indicators():
        """Get current indicator settings."""
        try:
            indicators = {
                "rsi": {"enabled": _settings.rsi.enabled, "name": "RSI"},
                "sma": {"enabled": _settings.sma.enabled, "name": "SMA Crossover"},
                "macd": {"enabled": _settings.macd.enabled, "name": "MACD"},
                "bollinger": {"enabled": _settings.bollinger.enabled, "name": "Bollinger Bands"}
            }
            return jsonify(indicators)
        except Exception as e:
            logger.exception("Failed to get indicators: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/indicators", methods=["PUT"])
    def update_indicators():
        """Update indicator enable/disable settings."""
        try:
            data = request.get_json()

            # Read current settings from file
            with open(_settings_path, "r") as f:
                settings_dict = yaml.safe_load(f)

            # Update indicator enabled flags
            if "rsi" in data:
                settings_dict["indicators"]["rsi"]["enabled"] = bool(data["rsi"])
            if "sma" in data:
                settings_dict["indicators"]["sma_crossover"]["enabled"] = bool(data["sma"])
            if "macd" in data:
                settings_dict["indicators"]["macd"]["enabled"] = bool(data["macd"])
            if "bollinger" in data:
                settings_dict["indicators"]["bollinger_bands"]["enabled"] = bool(data["bollinger"])

            # Save to file
            save_settings_to_file(_settings_path, settings_dict)

            # Reload settings in memory
            reload_settings(_settings_path)

            logger.info("Updated indicator settings: %s", data)
            return jsonify({"success": True, "updated": data}), 200

        except Exception as e:
            logger.exception("Failed to update indicators: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts")
    def get_accounts():
        """Get all trading accounts (without exposing secret keys)."""
        try:
            accounts_path = Path("config/accounts.yaml")
            accounts = load_accounts(accounts_path)

            # Remove secret keys from response for security
            safe_accounts = []
            for acc in accounts:
                safe_accounts.append({
                    "name": acc["name"],
                    "api_key": acc["api_key"][:8] + "..." if acc.get("api_key") else "",  # Show only first 8 chars
                    "paper": acc.get("paper", True),
                    "active": acc.get("active", False)
                })

            return jsonify(safe_accounts)
        except Exception as e:
            logger.exception("Failed to get accounts: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts", methods=["POST"])
    def create_account():
        """Add a new trading account."""
        try:
            data = request.get_json()
            name = data.get("name", "").strip()
            api_key = data.get("api_key", "").strip()
            secret_key = data.get("secret_key", "").strip()
            is_paper = data.get("paper", True)

            if not name:
                return jsonify({"error": "Account name is required"}), 400
            if not api_key or not secret_key:
                return jsonify({"error": "API key and secret key are required"}), 400

            accounts_path = Path("config/accounts.yaml")
            add_account(accounts_path, name, api_key, secret_key, is_paper)

            logger.info("Added new account: %s", name)
            return jsonify({"success": True, "name": name}), 201

        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        except Exception as e:
            logger.exception("Failed to create account: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts/<name>", methods=["PUT"])
    def edit_account(name: str):
        """Update an existing account."""
        try:
            data = request.get_json()
            api_key = data.get("api_key", "").strip()
            secret_key = data.get("secret_key", "").strip()
            is_paper = data.get("paper", True)

            if not api_key or not secret_key:
                return jsonify({"error": "API key and secret key are required"}), 400

            accounts_path = Path("config/accounts.yaml")
            success = update_account(accounts_path, name, api_key, secret_key, is_paper)

            if not success:
                return jsonify({"error": f"Account '{name}' not found"}), 404

            logger.info("Updated account: %s", name)
            return jsonify({"success": True, "name": name}), 200

        except Exception as e:
            logger.exception("Failed to update account: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts/<name>", methods=["DELETE"])
    def remove_account(name: str):
        """Delete an account."""
        try:
            accounts_path = Path("config/accounts.yaml")
            success = delete_account(accounts_path, name)

            if not success:
                return jsonify({"error": f"Account '{name}' not found"}), 404

            logger.info("Deleted account: %s", name)
            return jsonify({"success": True, "name": name}), 200

        except Exception as e:
            logger.exception("Failed to delete account: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts/<name>/activate", methods=["POST"])
    def activate_account(name: str):
        """Set an account as the active one."""
        try:
            accounts_path = Path("config/accounts.yaml")
            success = set_active_account(accounts_path, name)

            if not success:
                return jsonify({"error": f"Account '{name}' not found"}), 404

            logger.info("Activated account: %s", name)
            return jsonify({"success": True, "name": name, "message": "Please restart the dashboard to use this account"}), 200

        except Exception as e:
            logger.exception("Failed to activate account: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scheduler-status")
    def api_scheduler_status():
        running = _scheduler is not None and _scheduler.scheduler.running
        return jsonify({"running": running})

    @app.errorhandler(Exception)
    def handle_error(e):
        logger.exception("Dashboard API error: %s", e)
        return jsonify({"error": str(e)}), 500

    return app


def start_dashboard(
    config_path: str = "config/settings.yaml",
    watchlist_path: str = "config/watchlist.yaml",
    log_level: str = "INFO",
    dry_run: bool = False,
    host: str = "127.0.0.1",
    port: int = 5000,
    no_scheduler: bool = False,
):
    """Start the Flask dashboard with optional background trading scheduler."""
    global _client, _settings, _watchlist, _watchlist_raw, _pm, _scheduler, _watchlist_path, _settings_path

    setup_logger(level=log_level)

    _settings_path = Path(config_path)
    _settings = load_settings(_settings_path)

    _watchlist_path = Path(watchlist_path)
    _watchlist = load_watchlist(_watchlist_path)
    with open(watchlist_path, "r") as f:
        raw = yaml.safe_load(f)
    _watchlist_raw = raw["watchlist"]

    api_key, secret_key = load_api_keys()
    _client = AlpacaClient(api_key, secret_key, paper=True)
    _pm = PortfolioManager(_client)

    # Start background scheduler if enabled
    if not no_scheduler and _settings.schedule.enabled:
        def job():
            if _settings.schedule.market_hours_only and not _pm.is_market_open():
                logger.info("Market closed, skipping scheduled scan")
                return
            run_scan(_watchlist, _client, _settings, dry_run=dry_run, execute=True)

        _scheduler = TradingScheduler(job, _settings, blocking=False)
        _scheduler.start()
        logger.info("Background scheduler started")

    app = create_app()
    logger.info("Dashboard starting at http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False, use_reloader=False)
