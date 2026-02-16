"""Database models for multi-user support."""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication and multi-user support."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # 2FA fields
    totp_secret = db.Column(db.String(32), nullable=True)  # TOTP secret for 2FA
    is_2fa_enabled = db.Column(db.Boolean, default=False, nullable=False)

    # Account status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    accounts = db.relationship("Account", backref="user", lazy=True, cascade="all, delete-orphan")
    watchlists = db.relationship("Watchlist", backref="user", lazy=True, cascade="all, delete-orphan")
    settings = db.relationship("Settings", backref="user", uselist=False, cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", backref="user", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


class Account(db.Model):
    """Trading account model (Alpaca API credentials)."""

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    name = db.Column(db.String(100), nullable=False)
    api_key_encrypted = db.Column(db.Text, nullable=False)  # Encrypted API key
    secret_key_encrypted = db.Column(db.Text, nullable=False)  # Encrypted secret key
    is_paper = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Unique constraint: user can't have duplicate account names
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_user_account_name"),
    )

    def __repr__(self):
        return f"<Account {self.name} (User: {self.user_id})>"


class Watchlist(db.Model):
    """Watchlist model for tracking symbols per user."""

    __tablename__ = "watchlists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    symbol = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Unique constraint: user can't have duplicate symbols
    __table_args__ = (
        db.UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),
    )

    def __repr__(self):
        return f"<Watchlist {self.symbol} (User: {self.user_id})>"


class Settings(db.Model):
    """User-specific trading settings and indicator configurations."""

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # Data settings
    timeframe = db.Column(db.String(10), default="1Hour", nullable=False)
    lookback_days = db.Column(db.Integer, default=30, nullable=False)

    # RSI indicator
    rsi_enabled = db.Column(db.Boolean, default=True, nullable=False)
    rsi_period = db.Column(db.Integer, default=14, nullable=False)
    rsi_overbought = db.Column(db.Float, default=70.0, nullable=False)
    rsi_oversold = db.Column(db.Float, default=30.0, nullable=False)

    # SMA Crossover indicator
    sma_enabled = db.Column(db.Boolean, default=True, nullable=False)
    sma_short_period = db.Column(db.Integer, default=50, nullable=False)
    sma_long_period = db.Column(db.Integer, default=200, nullable=False)

    # MACD indicator
    macd_enabled = db.Column(db.Boolean, default=True, nullable=False)
    macd_fast_period = db.Column(db.Integer, default=12, nullable=False)
    macd_slow_period = db.Column(db.Integer, default=26, nullable=False)
    macd_signal_period = db.Column(db.Integer, default=9, nullable=False)

    # Bollinger Bands indicator
    bollinger_enabled = db.Column(db.Boolean, default=True, nullable=False)
    bollinger_period = db.Column(db.Integer, default=20, nullable=False)
    bollinger_std_dev = db.Column(db.Float, default=2.0, nullable=False)

    # Signal settings
    signal_mode = db.Column(db.String(20), default="majority", nullable=False)
    signal_min_agree = db.Column(db.Integer, default=2, nullable=False)

    # Execution settings
    execution_order_type = db.Column(db.String(20), default="market", nullable=False)
    execution_time_in_force = db.Column(db.String(20), default="day", nullable=False)
    execution_position_size_pct = db.Column(db.Float, default=10.0, nullable=False)
    execution_max_positions = db.Column(db.Integer, default=5, nullable=False)
    execution_allow_short = db.Column(db.Boolean, default=False, nullable=False)

    # Schedule settings
    schedule_enabled = db.Column(db.Boolean, default=False, nullable=False)
    schedule_interval_minutes = db.Column(db.Integer, default=60, nullable=False)
    schedule_cron = db.Column(db.String(50), nullable=True)
    schedule_market_hours_only = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Settings (User: {self.user_id})>"


class AuditLog(db.Model):
    """Audit log for tracking user actions."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    action = db.Column(db.String(50), nullable=False)  # e.g., "login", "create_account", "delete_watchlist"
    resource_type = db.Column(db.String(50), nullable=True)  # e.g., "account", "watchlist"
    resource_id = db.Column(db.Integer, nullable=True)  # ID of the affected resource
    details = db.Column(db.Text, nullable=True)  # JSON string with additional details

    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    user_agent = db.Column(db.String(200), nullable=True)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog {self.action} by User {self.user_id} at {self.timestamp}>"
