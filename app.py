"""Flask app entry point for Flask CLI (flask db migrate, flask db upgrade, etc.)."""
from alpaca_trader.dashboard_secure import create_app

app = create_app()
