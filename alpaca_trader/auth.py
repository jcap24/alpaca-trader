"""Authentication utilities and decorators."""
import functools
import json
import logging
from datetime import datetime

from flask import abort, request, session
from flask_login import LoginManager, current_user

from alpaca_trader.models import AuditLog, User, db

logger = logging.getLogger("alpaca_trader")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = "login_page"
login_manager.login_message = "Please log in to access this page."


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return db.session.get(User, int(user_id))


def login_required_2fa(f):
    """
    Decorator that requires both login AND 2FA verification if enabled.

    Use this instead of @login_required for sensitive operations.
    """

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        # Check if 2FA is enabled and verified in this session
        if current_user.is_2fa_enabled and not session.get("2fa_verified", False):
            abort(403, description="Two-factor authentication required")

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Decorator that requires admin privileges."""

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if not current_user.is_admin:
            abort(403, description="Admin privileges required")

        return f(*args, **kwargs)

    return decorated_function


def log_audit(action: str, resource_type: str = None, resource_id: int = None, details: dict = None):
    """
    Log an audit event.

    Args:
        action: Action performed (e.g., "login", "create_account")
        resource_type: Type of resource affected (e.g., "account", "watchlist")
        resource_id: ID of the affected resource
        details: Additional details as a dictionary
    """
    try:
        user_id = current_user.id if current_user.is_authenticated else None

        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:200],
        )

        db.session.add(audit_log)
        db.session.commit()

        logger.info(
            "Audit: %s by user %s (IP: %s)",
            action,
            user_id or "anonymous",
            request.remote_addr,
        )

    except Exception as e:
        logger.error("Failed to log audit event: %s", e)
        # Don't fail the request if audit logging fails
        db.session.rollback()


def update_last_login(user: User):
    """Update user's last login timestamp."""
    try:
        user.last_login = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        logger.error("Failed to update last login for user %s: %s", user.id, e)
        db.session.rollback()
