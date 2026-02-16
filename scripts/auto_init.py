"""Auto-initialize database and create admin user from environment variables.

This script is designed to run automatically on deployment (via Procfile release command).
It will:
1. Create database tables if they don't exist
2. Create an admin user from environment variables if no users exist
"""

import os
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alpaca_trader.models import db, User
from alpaca_trader.security import PasswordManager
from alpaca_trader.dashboard_secure import create_app


def init_database():
    """Initialize database tables."""
    app = create_app()

    with app.app_context():
        # Create all tables
        db.create_all()
        print("[SUCCESS] Database tables created/verified")

        # Check if any users exist
        user_count = User.query.count()

        if user_count == 0:
            # Create admin user from environment variables
            admin_username = os.getenv("ADMIN_USERNAME", "admin")
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD")

            if not admin_password:
                print("[WARNING] No ADMIN_PASSWORD environment variable set!")
                print("[WARNING] Please set ADMIN_PASSWORD in Render environment variables")
                print("[WARNING] Skipping admin user creation")
                return

            # Create admin user
            pm = PasswordManager()
            password_hash = pm.hash_password(admin_password)

            admin_user = User(
                username=admin_username,
                email=admin_email,
                password_hash=password_hash,
                role="admin",
                is_2fa_enabled=False
            )

            db.session.add(admin_user)
            db.session.commit()

            print(f"[SUCCESS] Admin user created: {admin_username}")
            print(f"[INFO] Email: {admin_email}")
            print("[INFO] You can now log in with these credentials")
        else:
            print(f"[INFO] Database already has {user_count} user(s), skipping admin creation")


if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
