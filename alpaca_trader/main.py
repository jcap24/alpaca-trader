import argparse
import logging
from pathlib import Path

from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import load_api_keys, load_settings, load_watchlist
from alpaca_trader.data import fetch_bars
from alpaca_trader.executor import OrderExecutor
from alpaca_trader.indicators import compute_all
from alpaca_trader.logger import setup_logger
from alpaca_trader.portfolio import PortfolioManager
from alpaca_trader.signals import Action, evaluate_signals

logger = logging.getLogger("alpaca_trader")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpaca-trader",
        description="Signal-based stock trading bot using Alpaca paper trading",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to settings YAML file",
    )
    parser.add_argument(
        "--watchlist",
        type=str,
        default="config/watchlist.yaml",
        help="Path to watchlist YAML file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan: check signals (read-only, never trades)
    scan_parser = subparsers.add_parser("scan", help="Scan watchlist for trading signals")
    scan_parser.add_argument("--symbol", type=str, help="Scan a single symbol")

    # trade: scan + execute
    trade_parser = subparsers.add_parser("trade", help="Scan for signals and execute trades")
    trade_parser.add_argument("--dry-run", action="store_true", help="Show trades without executing")
    trade_parser.add_argument("--symbol", type=str, help="Trade a single symbol")

    # schedule: run on a timer
    schedule_parser = subparsers.add_parser("schedule", help="Start scheduled trading")
    schedule_parser.add_argument("--dry-run", action="store_true", help="Scheduled mode without real orders")

    # status: show portfolio
    subparsers.add_parser("status", help="Show account and position summary")

    # backtest: historical signal analysis
    backtest_parser = subparsers.add_parser("backtest", help="Run signals against historical data")
    backtest_parser.add_argument("--days", type=int, default=30, help="Days to backtest")
    backtest_parser.add_argument("--symbol", type=str, help="Backtest a single symbol")

    # dashboard: web UI (legacy single-user)
    dashboard_parser = subparsers.add_parser("dashboard", help="Start the web dashboard (legacy, single-user)")
    dashboard_parser.add_argument("--host", type=str, default="127.0.0.1", help="Dashboard host")
    dashboard_parser.add_argument("--port", type=int, default=5000, help="Dashboard port")
    dashboard_parser.add_argument("--dry-run", action="store_true", help="Scheduler runs without real orders")
    dashboard_parser.add_argument("--no-scheduler", action="store_true", help="Start dashboard without trading scheduler")

    # dashboard-secure: secure multi-user web UI
    dashboard_secure_parser = subparsers.add_parser("dashboard-secure", help="Start secure multi-user dashboard (production)")
    dashboard_secure_parser.add_argument("--host", type=str, default="127.0.0.1", help="Dashboard host")
    dashboard_secure_parser.add_argument("--port", type=int, default=5000, help="Dashboard port")
    dashboard_secure_parser.add_argument("--no-scheduler", action="store_true", help="Start dashboard without trading scheduler")

    return parser


def run_scan(symbols, client, settings, dry_run=False, execute=False):
    """Core logic: fetch data, compute indicators, evaluate signals, optionally trade."""
    bars = fetch_bars(client, symbols, settings.data.timeframe, settings.data.lookback_days)

    executor = OrderExecutor(client, settings) if execute else None
    results = []

    for symbol, df in bars.items():
        df = compute_all(df, settings)
        signal = evaluate_signals(df, symbol, settings)

        status_icon = {"buy": "+", "sell": "-", "hold": " "}[signal.action.value]
        logger.info(
            "[%s] %s: %s (strength=%.0f%%) | %s",
            status_icon,
            symbol,
            signal.action.value.upper(),
            signal.strength * 100,
            signal.details,
        )

        if execute and signal.action != Action.HOLD and executor:
            result = executor.execute_signal(signal, dry_run=dry_run)
            if result:
                results.append(result)

    if execute and results:
        logger.info("--- %d order(s) processed ---", len(results))
    elif execute:
        logger.info("--- No trades triggered ---")

    return results


def cmd_status(client):
    """Print account summary and open positions."""
    pm = PortfolioManager(client)
    summary = pm.get_summary()

    print("\n=== Account Summary ===")
    print(f"  Equity:       ${summary['equity']:,.2f}")
    print(f"  Cash:         ${summary['cash']:,.2f}")
    print(f"  Buying Power: ${summary['buying_power']:,.2f}")
    print(f"  Portfolio:    ${summary['portfolio_value']:,.2f}")

    positions = pm.get_positions_summary()
    if positions:
        print(f"\n=== Open Positions ({len(positions)}) ===")
        print(f"  {'Symbol':<8} {'Qty':>8} {'Value':>12} {'P&L':>12} {'P&L %':>8}")
        print(f"  {'-'*8} {'-'*8} {'-'*12} {'-'*12} {'-'*8}")
        for p in positions:
            print(
                f"  {p['symbol']:<8} {p['qty']:>8.2f} "
                f"${p['market_value']:>10,.2f} "
                f"${p['unrealized_pl']:>10,.2f} "
                f"{p['unrealized_plpc']:>7.2%}"
            )
    else:
        print("\n  No open positions.")
    print()


def cmd_backtest(symbols, client, settings, days):
    """Run signals over historical data and report what would have triggered."""
    settings_copy = settings
    # Override lookback for backtest
    from dataclasses import replace
    from alpaca_trader.config import DataConfig

    data_config = replace(settings.data, lookback_days=days)
    settings_copy = replace(settings, data=data_config)

    bars = fetch_bars(
        client, symbols, settings_copy.data.timeframe, settings_copy.data.lookback_days
    )

    print(f"\n=== Backtest Results ({days} days) ===\n")

    for symbol, df in bars.items():
        df = compute_all(df, settings_copy)

        buy_signals = 0
        sell_signals = 0

        for i in range(len(df)):
            row_df = df.iloc[: i + 1]
            signal = evaluate_signals(row_df, symbol, settings_copy)
            if signal.action == Action.BUY:
                buy_signals += 1
            elif signal.action == Action.SELL:
                sell_signals += 1

        price_start = df["close"].iloc[0]
        price_end = df["close"].iloc[-1]
        price_change = ((price_end - price_start) / price_start) * 100

        print(f"  {symbol}:")
        print(f"    Price: ${price_start:.2f} -> ${price_end:.2f} ({price_change:+.1f}%)")
        print(f"    Buy signals:  {buy_signals}")
        print(f"    Sell signals: {sell_signals}")
        print()


def main():
    parser = build_parser()
    args = parser.parse_args()

    setup_logger(level=args.log_level)
    settings = load_settings(Path(args.config))
    watchlist = load_watchlist(Path(args.watchlist))
    api_key, secret_key = load_api_keys()
    client = AlpacaClient(api_key, secret_key, paper=True)

    if args.command == "scan":
        symbols = [args.symbol] if args.symbol else watchlist
        run_scan(symbols, client, settings, execute=False)

    elif args.command == "trade":
        symbols = [args.symbol] if args.symbol else watchlist
        run_scan(
            symbols,
            client,
            settings,
            dry_run=getattr(args, "dry_run", False),
            execute=True,
        )

    elif args.command == "schedule":
        from alpaca_trader.scheduler import TradingScheduler

        pm = PortfolioManager(client)
        dry_run = getattr(args, "dry_run", False)

        def job():
            if settings.schedule.market_hours_only and not pm.is_market_open():
                logger.info("Market closed, skipping scan")
                return
            run_scan(watchlist, client, settings, dry_run=dry_run, execute=True)

        scheduler = TradingScheduler(job, settings)
        scheduler.start()

    elif args.command == "status":
        cmd_status(client)

    elif args.command == "backtest":
        symbols = [args.symbol] if getattr(args, "symbol", None) else watchlist
        cmd_backtest(symbols, client, settings, args.days)

    elif args.command == "dashboard":
        from alpaca_trader.dashboard import start_dashboard

        start_dashboard(
            config_path=args.config,
            watchlist_path=args.watchlist,
            log_level=args.log_level,
            dry_run=getattr(args, "dry_run", False),
            host=args.host,
            port=args.port,
            no_scheduler=getattr(args, "no_scheduler", False),
        )

    elif args.command == "dashboard-secure":
        from alpaca_trader.dashboard_secure import start_dashboard_secure

        start_dashboard_secure(
            host=args.host,
            port=args.port,
            no_scheduler=getattr(args, "no_scheduler", False),
        )


if __name__ == "__main__":
    main()
