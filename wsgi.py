"""WSGI entry point for production deployment."""

from alpaca_trader.dashboard_secure import create_app

# Create the Flask application instance
app = create_app()

if __name__ == "__main__":
    app.run()
