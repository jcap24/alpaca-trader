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

    # Fix DATABASE_URL for Render's PostgreSQL (requires SSL)
    database_url = os.getenv("DATABASE_URL", "sqlite:///alpaca_trader.db")
    if database_url.startswith("postgres://"):
        # Render uses postgres:// but SQLAlchemy 1.4+ requires postgresql://
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Add SSL mode for PostgreSQL connections
    if database_url.startswith("postgresql://") and "sslmode" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    # Configuration
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", os.urandom(32)),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
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

    # Auto-initialize database on first run
    with app.app_context():
        try:
            # Create all tables if they don't exist
            db.create_all()
            logger.info("Database tables created/verified")

            # Create default admin user if no users exist
            if User.query.count() == 0:
                admin_username = os.getenv("ADMIN_USERNAME", "admin")
                admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
                admin_password = os.getenv("ADMIN_PASSWORD")

                if admin_password:
                    pm = PasswordManager()
                    password_hash = pm.hash_password(admin_password)

                    admin_user = User(
                        username=admin_username,
                        email=admin_email,
                        password_hash=password_hash,
                        role="admin",
                        is_2fa_enabled=False,
                    )

                    db.session.add(admin_user)
                    db.session.commit()
                    logger.info("Default admin user created: %s", admin_username)
                else:
                    logger.warning("ADMIN_PASSWORD not set, skipping admin user creation")
        except Exception as e:
            logger.error("Database initialization failed: %s", e)
            # Don't crash the app, continue anyway

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

    # =============================================================================
    # Signals API
    # =============================================================================

    @app.route("/api/signals")
    @login_required
    def api_signals():
        """Get trading signals for user's watchlist."""
        try:
            # Get user's watchlist
            watchlist_entries = Watchlist.query.filter_by(user_id=current_user.id).all()
            symbols = [entry.symbol for entry in watchlist_entries]

            if not symbols:
                return jsonify([])

            # Get user's settings
            settings = SettingsModel.query.filter_by(user_id=current_user.id).first()
            if not settings:
                return jsonify({"error": "Settings not configured"}), 400

            # Convert DB settings to Settings dataclass
            from alpaca_trader.config import (
                RSIConfig, SMAConfig, MACDConfig, BollingerConfig,
                SignalConfig, ExecutionConfig, DataConfig, ScheduleConfig, Settings
            )

            settings_obj = Settings(
                rsi=RSIConfig(
                    enabled=settings.rsi_enabled,
                    period=settings.rsi_period,
                    overbought=settings.rsi_overbought,
                    oversold=settings.rsi_oversold
                ),
                sma=SMAConfig(
                    enabled=settings.sma_enabled,
                    short_period=settings.sma_short_period,
                    long_period=settings.sma_long_period
                ),
                macd=MACDConfig(
                    enabled=settings.macd_enabled,
                    fast_period=settings.macd_fast_period,
                    slow_period=settings.macd_slow_period,
                    signal_period=settings.macd_signal_period
                ),
                bollinger=BollingerConfig(
                    enabled=settings.bollinger_enabled,
                    period=settings.bollinger_period,
                    std_dev=settings.bollinger_std_dev
                ),
                signal=SignalConfig(
                    mode=settings.signal_mode,
                    min_agree=settings.signal_min_agree
                ),
                execution=ExecutionConfig(
                    order_type=settings.execution_order_type,
                    time_in_force=settings.execution_time_in_force,
                    position_size_pct=settings.execution_position_size_pct,
                    max_positions=settings.execution_max_positions,
                    allow_short=settings.execution_allow_short
                ),
                data=DataConfig(
                    timeframe=settings.timeframe,
                    lookback_days=settings.lookback_days
                ),
                schedule=ScheduleConfig(
                    enabled=settings.schedule_enabled,
                    interval_minutes=settings.schedule_interval_minutes,
                    cron=settings.schedule_cron,
                    market_hours_only=settings.schedule_market_hours_only
                )
            )

            # Fetch bars and compute signals
            client = get_user_client()
            bars = fetch_bars(client, symbols, settings_obj.data.timeframe, settings_obj.data.lookback_days)

            results = []
            for symbol, df in bars.items():
                df = compute_all(df, settings_obj)
                signal = evaluate_signals(df, symbol, settings_obj)

                # Get name from watchlist
                name = symbol
                for entry in watchlist_entries:
                    if entry.symbol == symbol:
                        name = entry.name or symbol
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

        except Exception as e:
            logger.exception("Failed to get signals: %s", e)
            return jsonify({"error": str(e)}), 500

    # =============================================================================
    # Watchlist Management API
    # =============================================================================

    @app.route("/api/watchlist")
    @login_required
    def api_watchlist():
        """Get user's watchlist."""
        entries = Watchlist.query.filter_by(user_id=current_user.id).order_by(Watchlist.created_at).all()
        return jsonify([{"symbol": e.symbol, "name": e.name} for e in entries])

    @app.route("/api/watchlist", methods=["POST"])
    @login_required
    @limiter.limit("20 per minute")
    @csrf.exempt
    def add_watchlist_symbol():
        """Add a symbol to user's watchlist."""
        try:
            data = request.get_json()
            symbol = data.get("symbol", "").strip().upper()

            # Validate symbol format
            if not symbol or not symbol.isalpha() or len(symbol) > 5:
                return jsonify({"error": "Symbol must be 1-5 letters"}), 400

            # Check for duplicates
            existing = Watchlist.query.filter_by(user_id=current_user.id, symbol=symbol).first()
            if existing:
                return jsonify({"error": f"Symbol {symbol} already in watchlist"}), 409

            # Validate with Alpaca API
            client = get_user_client()
            asset = client.get_asset(symbol)
            if asset is None:
                return jsonify({"error": f"Symbol {symbol} not found. Please verify it's a valid ticker."}), 404

            # Get company name
            name = asset.name if hasattr(asset, 'name') and asset.name else symbol

            # Add to watchlist
            entry = Watchlist(user_id=current_user.id, symbol=symbol, name=name)
            db.session.add(entry)
            db.session.commit()

            log_audit("watchlist_add", "watchlist", entry.id, {"symbol": symbol})
            logger.info("User %s added %s to watchlist", current_user.username, symbol)

            return jsonify({"success": True, "symbol": symbol, "name": name}), 201

        except Exception as e:
            logger.exception("Failed to add symbol: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/watchlist/<symbol>", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def remove_watchlist_symbol(symbol: str):
        """Remove a symbol from user's watchlist."""
        try:
            symbol = symbol.upper()
            entry = Watchlist.query.filter_by(user_id=current_user.id, symbol=symbol).first()

            if not entry:
                return jsonify({"error": f"Symbol {symbol} not found in watchlist"}), 404

            db.session.delete(entry)
            db.session.commit()

            log_audit("watchlist_remove", "watchlist", entry.id, {"symbol": symbol})
            logger.info("User %s removed %s from watchlist", current_user.username, symbol)

            return jsonify({"success": True, "symbol": symbol}), 200

        except Exception as e:
            logger.exception("Failed to remove symbol: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    # =============================================================================
    # Indicator Settings API
    # =============================================================================

    @app.route("/api/indicators")
    @login_required
    def get_indicators():
        """Get user's indicator settings."""
        try:
            settings = SettingsModel.query.filter_by(user_id=current_user.id).first()
            if not settings:
                return jsonify({"error": "Settings not found"}), 404

            return jsonify({
                "rsi": {"enabled": settings.rsi_enabled, "name": "RSI"},
                "sma": {"enabled": settings.sma_enabled, "name": "SMA Crossover"},
                "macd": {"enabled": settings.macd_enabled, "name": "MACD"},
                "bollinger": {"enabled": settings.bollinger_enabled, "name": "Bollinger Bands"}
            })

        except Exception as e:
            logger.exception("Failed to get indicators: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/indicators", methods=["PUT"])
    @login_required
    @csrf.exempt
    def update_indicators():
        """Update user's indicator enable/disable settings."""
        try:
            data = request.get_json()
            settings = SettingsModel.query.filter_by(user_id=current_user.id).first()

            if not settings:
                return jsonify({"error": "Settings not found"}), 404

            # Update indicator flags
            if "rsi" in data:
                settings.rsi_enabled = bool(data["rsi"])
            if "sma" in data:
                settings.sma_enabled = bool(data["sma"])
            if "macd" in data:
                settings.macd_enabled = bool(data["macd"])
            if "bollinger" in data:
                settings.bollinger_enabled = bool(data["bollinger"])

            db.session.commit()

            log_audit("indicators_update", "settings", settings.id, data)
            logger.info("User %s updated indicators: %s", current_user.username, data)

            return jsonify({"success": True, "updated": data}), 200

        except Exception as e:
            logger.exception("Failed to update indicators: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    # =============================================================================
    # Trading Accounts Management API
    # =============================================================================

    @app.route("/api/accounts")
    @login_required
    def get_accounts():
        """Get user's trading accounts (without exposing secret keys)."""
        try:
            accounts = Account.query.filter_by(user_id=current_user.id).order_by(Account.created_at).all()

            safe_accounts = []
            for acc in accounts:
                # Decrypt API key to show preview
                try:
                    api_key = _encryption_manager.decrypt(acc.api_key_encrypted)
                    api_key_preview = api_key[:8] + "..." if api_key else "***"
                except:
                    api_key_preview = "***"

                safe_accounts.append({
                    "name": acc.name,
                    "api_key": api_key_preview,
                    "paper": acc.is_paper,
                    "active": acc.is_active
                })

            return jsonify(safe_accounts)

        except Exception as e:
            logger.exception("Failed to get accounts: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts", methods=["POST"])
    @login_required
    @limiter.limit("10 per hour")
    @csrf.exempt
    def create_account():
        """Add a new trading account."""
        try:
            data = request.get_json()
            name = data.get("name", "").strip()
            api_key = data.get("api_key", "").strip()
            secret_key = data.get("secret_key", "").strip()
            is_paper = data.get("paper", True)

            # Validation
            if not name:
                return jsonify({"error": "Account name is required"}), 400
            if not api_key or not secret_key:
                return jsonify({"error": "API key and secret key are required"}), 400

            # Check for duplicate name
            existing = Account.query.filter_by(user_id=current_user.id, name=name).first()
            if existing:
                return jsonify({"error": f"Account '{name}' already exists"}), 409

            # Encrypt keys
            api_key_encrypted = _encryption_manager.encrypt(api_key)
            secret_key_encrypted = _encryption_manager.encrypt(secret_key)

            # If first account, make it active
            is_active = Account.query.filter_by(user_id=current_user.id).count() == 0

            # Create account
            account = Account(
                user_id=current_user.id,
                name=name,
                api_key_encrypted=api_key_encrypted,
                secret_key_encrypted=secret_key_encrypted,
                is_paper=is_paper,
                is_active=is_active
            )

            db.session.add(account)
            db.session.commit()

            log_audit("account_create", "account", account.id, {"name": name, "paper": is_paper})
            logger.info("User %s created account: %s", current_user.username, name)

            return jsonify({"success": True, "name": name}), 201

        except Exception as e:
            logger.exception("Failed to create account: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts/<name>", methods=["PUT"])
    @login_required
    @csrf.exempt
    def edit_account(name: str):
        """Update an existing trading account."""
        try:
            data = request.get_json()
            api_key = data.get("api_key", "").strip()
            secret_key = data.get("secret_key", "").strip()
            is_paper = data.get("paper", True)

            if not api_key or not secret_key:
                return jsonify({"error": "API key and secret key are required"}), 400

            account = Account.query.filter_by(user_id=current_user.id, name=name).first()
            if not account:
                return jsonify({"error": f"Account '{name}' not found"}), 404

            # Encrypt and update
            account.api_key_encrypted = _encryption_manager.encrypt(api_key)
            account.secret_key_encrypted = _encryption_manager.encrypt(secret_key)
            account.is_paper = is_paper

            db.session.commit()

            log_audit("account_update", "account", account.id, {"name": name})
            logger.info("User %s updated account: %s", current_user.username, name)

            return jsonify({"success": True, "name": name}), 200

        except Exception as e:
            logger.exception("Failed to update account: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts/<name>", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def remove_account(name: str):
        """Delete a trading account."""
        try:
            account = Account.query.filter_by(user_id=current_user.id, name=name).first()
            if not account:
                return jsonify({"error": f"Account '{name}' not found"}), 404

            was_active = account.is_active
            account_id = account.id

            db.session.delete(account)

            # If deleted account was active, activate another one
            if was_active:
                next_account = Account.query.filter_by(user_id=current_user.id).first()
                if next_account:
                    next_account.is_active = True

            db.session.commit()

            log_audit("account_delete", "account", account_id, {"name": name})
            logger.info("User %s deleted account: %s", current_user.username, name)

            return jsonify({"success": True, "name": name}), 200

        except Exception as e:
            logger.exception("Failed to delete account: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/accounts/<name>/activate", methods=["POST"])
    @login_required
    @csrf.exempt
    def activate_account(name: str):
        """Set a trading account as active."""
        try:
            account = Account.query.filter_by(user_id=current_user.id, name=name).first()
            if not account:
                return jsonify({"error": f"Account '{name}' not found"}), 404

            # Deactivate all others, activate this one
            Account.query.filter_by(user_id=current_user.id).update({"is_active": False})
            account.is_active = True
            db.session.commit()

            log_audit("account_activate", "account", account.id, {"name": name})
            logger.info("User %s activated account: %s", current_user.username, name)

            return jsonify({
                "success": True,
                "name": name,
                "message": "Account activated successfully"
            }), 200

        except Exception as e:
            logger.exception("Failed to activate account: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    # =============================================================================
    # Scheduler Status API
    # =============================================================================

    @app.route("/api/scheduler-status")
    @login_required
    def api_scheduler_status():
        """Get scheduler status."""
        running = _scheduler is not None and _scheduler.scheduler.running if _scheduler else False
        return jsonify({"running": running})

    # =============================================================================
    # 2FA Management API
    # =============================================================================

    @app.route("/api/2fa/setup", methods=["POST"])
    @login_required
    @csrf.exempt
    def setup_2fa():
        """Generate 2FA secret for setup."""
        try:
            if current_user.is_2fa_enabled:
                return jsonify({"error": "2FA is already enabled"}), 400

            # Generate new secret
            secret = TwoFactorAuth.generate_secret()

            # Store temporarily in session (not saved to DB until verified)
            session["2fa_setup_secret"] = secret

            return jsonify({
                "success": True,
                "secret": secret,
                "qr_url": f"/api/2fa/qrcode?secret={secret}"
            }), 200

        except Exception as e:
            logger.exception("Failed to setup 2FA: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/2fa/qrcode")
    @login_required
    def get_2fa_qrcode():
        """Get QR code for 2FA setup."""
        try:
            secret = session.get("2fa_setup_secret") or current_user.totp_secret
            if not secret:
                return jsonify({"error": "No 2FA setup in progress"}), 400

            qr_buffer = TwoFactorAuth.generate_qr_code(
                secret,
                current_user.username,
                "Alpaca Trader"
            )

            return send_file(qr_buffer, mimetype="image/png")

        except Exception as e:
            logger.exception("Failed to generate QR code: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/2fa/enable", methods=["POST"])
    @login_required
    @csrf.exempt
    def enable_2fa():
        """Enable 2FA after verifying token."""
        try:
            data = request.get_json()
            token = data.get("token", "").strip()

            secret = session.get("2fa_setup_secret")
            if not secret:
                return jsonify({"error": "No 2FA setup in progress"}), 400

            # Verify token
            if not TwoFactorAuth.verify_totp(secret, token):
                return jsonify({"error": "Invalid verification code"}), 401

            # Enable 2FA
            current_user.totp_secret = secret
            current_user.is_2fa_enabled = True
            db.session.commit()

            session.pop("2fa_setup_secret", None)

            log_audit("2fa_enable")
            logger.info("User %s enabled 2FA", current_user.username)

            return jsonify({"success": True, "message": "2FA enabled successfully"}), 200

        except Exception as e:
            logger.exception("Failed to enable 2FA: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/2fa/disable", methods=["POST"])
    @login_required
    @csrf.exempt
    def disable_2fa():
        """Disable 2FA (requires password confirmation)."""
        try:
            data = request.get_json()
            password = data.get("password", "")

            # Verify password
            if not PasswordManager.verify_password(password, current_user.password_hash):
                return jsonify({"error": "Invalid password"}), 401

            # Disable 2FA
            current_user.is_2fa_enabled = False
            current_user.totp_secret = None
            db.session.commit()

            log_audit("2fa_disable")
            logger.info("User %s disabled 2FA", current_user.username)

            return jsonify({"success": True, "message": "2FA disabled successfully"}), 200

        except Exception as e:
            logger.exception("Failed to disable 2FA: %s", e)
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    return app


def start_dashboard_secure(
    host: str = "127.0.0.1",
    port: int = 5000,
    no_scheduler: bool = False,
):
    """Start the secure dashboard with optional background scheduler."""
    global _encryption_manager, _client, _pm, _scheduler

    # Load environment variables from .env file
    from dotenv import load_dotenv
    load_dotenv()

    # Initialize encryption manager
    _encryption_manager = EncryptionManager()

    # Create Flask app
    app = create_app()

    # Initialize database
    with app.app_context():
        db.create_all()
        logger.info("Database initialized")

    # Start background scheduler (future feature)
    # if not no_scheduler:
    #     # TODO: Implement user-specific schedulers
    #     pass

    logger.info("Secure dashboard starting at http://%s:%d", host, port)
    logger.info("Login at: http://%s:%d/login", host, port)

    # Run Flask app
    app.run(host=host, port=port, debug=os.getenv("FLASK_ENV") != "production")


if __name__ == "__main__":
    start_dashboard_secure()
