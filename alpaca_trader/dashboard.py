import logging
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import load_api_keys, load_settings, load_watchlist
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
    global _client, _settings, _watchlist, _watchlist_raw, _pm, _scheduler

    setup_logger(level=log_level)

    _settings = load_settings(Path(config_path))

    _watchlist = load_watchlist(Path(watchlist_path))
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
