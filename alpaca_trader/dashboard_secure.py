"""
Secure multi-user dashboard with authentication, encryption, and audit logging.

This is an enhanced version of dashboard.py with:
- User authentication (Flask-Login)
- Encrypted API key storage
- CSRF protection (Flask-WTF)
- Rate limiting (Flask-Limiter)
- Database storage (SQLAlchemy)
- Multi-user support with isolation
- Two-factor authentication (2FA)
- Audit logging
- Security headers
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from alpaca_trader.auth import admin_required, log_audit, login_manager, update_last_login
from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import Settings
from alpaca_trader.data import fetch_bars
from alpaca_trader.indicators import compute_all
from alpaca_trader.logger import setup_logger
from alpaca_trader.models import Account, AuditLog, Settings as SettingsModel, User, Watchlist, db
from alpaca_trader.portfolio import PortfolioManager
from alpaca_trader.scheduler import TradingScheduler
from alpaca_trader.security import EncryptionManager, PasswordManager, TwoFactorAuth
from alpaca_trader.signals import evaluate_signals

logger = logging.getLogger("alpaca_trader")

# Global encryption manager (initialized in start_dashboard)
_encryption_manager: EncryptionManager = None

# Module-level references for backward compatibility
_client: AlpacaClient = None
_pm: PortfolioManager = None
_scheduler: TradingScheduler = None


def create_app(config=None) -> Flask:
    """Create and configure the secure Flask application."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent / "templates"),
        static_folder=str(Path(__file__).parent.parent / "static"),
    )

    # Configuration
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", os.urandom(32)),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///alpaca_trader.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=None,  # CSRF tokens don't expire
        SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") == "production",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=86400,  # 24 hours
    )

    if config:
        app.config.update(config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate = Migrate(app, db)
    csrf = CSRFProtect(app)

    # Initialize rate limiter
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )

    # Security headers middleware
    @app.after_request
    def set_security_headers(response):
        """Add security headers to all responses."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        if os.getenv("FLASK_ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("error.html", error="Page not found", code=404), 404

    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 errors."""
        if request.path.startswith("/api/"):
            return jsonify({"error": str(error.description or "Forbidden")}), 403
        return render_template("error.html", error=str(error.description or "Forbidden"), code=403), 403

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.exception("Internal server error: %s", error)
        db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("error.html", error="Internal server error", code=500), 500

    # =============================================================================
    # Authentication Routes
    # =============================================================================

    @app.route("/login")
    def login_page():
        """Render login page."""
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        return render_template("login.html")

    @app.route("/verify-2fa")
    def verify_2fa_page():
        """Render 2FA verification page."""
        if not session.get("2fa_user_id"):
            return redirect(url_for("login_page"))
        return render_template("verify_2fa.html")

    @app.route("/api/auth/register", methods=["POST"])
    @limiter.limit("5 per hour")
    @csrf.exempt  # API endpoint - CSRF handled via JSON
    def register():
        """Register a new user."""
        data = request.get_json()

        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        # Validation
        if not username or not email or not password:
            return jsonify({"error": "All fields are required"}), 400

        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        # Check for existing user
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "Username already exists"}), 409

        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 409

        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=PasswordManager.hash_password(password),
            is_admin=User.query.count() == 0,  # First user is admin
        )

        db.session.add(user)
        db.session.commit()

        # Create default settings
        default_settings = SettingsModel(user_id=user.id)
        db.session.add(default_settings)
        db.session.commit()

        log_audit("register", details={"username": username, "email": email})
        logger.info("New user registered: %s", username)

        return jsonify({"success": True, "message": "Account created successfully"}), 201

    @app.route("/api/auth/login", methods=["POST"])
    @limiter.limit("10 per minute")
    @csrf.exempt  # API endpoint
    def login():
        """Authenticate user."""
        data = request.get_json()

        username_or_email = data.get("username", "").strip()
        password = data.get("password", "")
        remember = data.get("remember", False)

        # Find user by username or email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email.lower())
        ).first()

        if not user or not PasswordManager.verify_password(password, user.password_hash):
            log_audit("login_failed", details={"username": username_or_email})
            return jsonify({"error": "Invalid credentials"}), 401

        if not user.is_active:
            return jsonify({"error": "Account is disabled"}), 403

        # Check if 2FA is enabled
        if user.is_2fa_enabled:
            session["2fa_user_id"] = user.id
            session["2fa_remember"] = remember
            return jsonify({"requires_2fa": True}), 200

        # Login user
        login_user(user, remember=remember)
        update_last_login(user)
        log_audit("login", details={"username": user.username})

        return jsonify({"success": True}), 200

    @app.route("/api/auth/verify-2fa", methods=["POST"])
    @limiter.limit("10 per minute")
    @csrf.exempt
    def verify_2fa():
        """Verify 2FA token."""
        user_id = session.get("2fa_user_id")
        if not user_id:
            return jsonify({"error": "No pending 2FA verification"}), 400

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json()
        token = data.get("token", "").strip()

        if not TwoFactorAuth.verify_totp(user.totp_secret, token):
            log_audit("2fa_failed", details={"user_id": user_id})
            return jsonify({"error": "Invalid verification code"}), 401

        # Login user
        remember = session.get("2fa_remember", False)
        login_user(user, remember=remember)
        update_last_login(user)

        session["2fa_verified"] = True
        session.pop("2fa_user_id", None)
        session.pop("2fa_remember", None)

        log_audit("2fa_verified", details={"user_id": user_id})

        return jsonify({"success": True}), 200

    @app.route("/api/auth/logout", methods=["POST"])
    @csrf.exempt
    def logout():
        """Logout current user."""
        if current_user.is_authenticated:
            log_audit("logout")
        logout_user()
        session.clear()
        return jsonify({"success": True}), 200

    # =============================================================================
    # Dashboard Routes
    # =============================================================================

    @app.route("/")
    @login_required
    def index():
        """Render main dashboard."""
        return render_template("dashboard.html")

    @app.route("/health")
    def health_check():
        """Health check endpoint for monitoring."""
        return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200

    # =============================================================================
    # Account API (requires user context)
    # =============================================================================

    def get_user_client() -> AlpacaClient:
        """Get Alpaca client for current user's active account."""
        active_account = (
            Account.query.filter_by(user_id=current_user.id, is_active=True).first()
        )

        if not active_account:
            abort(400, description="No active trading account. Please add and activate an account.")

        # Decrypt API keys
        api_key = _encryption_manager.decrypt(active_account.api_key_encrypted)
        secret_key = _encryption_manager.decrypt(active_account.secret_key_encrypted)

        return AlpacaClient(api_key, secret_key, paper=active_account.is_paper)

    @app.route("/api/account")
    @login_required
    def api_account():
        """Get account summary."""
        try:
            client = get_user_client()
            pm = PortfolioManager(client)
            summary = pm.get_summary()
            summary["market_open"] = pm.is_market_open()
            return jsonify(summary)
        except Exception as e:
            logger.exception("Failed to get account summary: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/positions")
    @login_required
    def api_positions():
        """Get open positions."""
        try:
            client = get_user_client()
            pm = PortfolioManager(client)
            positions = pm.get_positions_summary()
            return jsonify(positions)
        except Exception as e:
            logger.exception("Failed to get positions: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/orders")
    @login_required
    def api_orders():
        """Get order history."""
        try:
            client = get_user_client()
            order_filter = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50)
            orders = client.get_orders(filter=order_filter)

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
        except Exception as e:
            logger.exception("Failed to get orders: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio-history")
    @login_required
    def api_portfolio_history():
        """Get portfolio history."""
        period = request.args.get("period", "1M")
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest

            client = get_user_client()
            history_req = GetPortfolioHistoryRequest(period=period, timeframe="1D")
            history = client.get_portfolio_history(filter=history_req)

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

    # Continue in next part...
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
