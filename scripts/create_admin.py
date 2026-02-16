"""Create an admin user for the Alpaca Trader dashboard."""
import sys
from getpass import getpass
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alpaca_trader.dashboard_secure import create_app
from alpaca_trader.models import Settings as SettingsModel, User, db
from alpaca_trader.security import PasswordManager


def create_admin_user():
    """Interactive script to create an admin user."""
    print("=" * 60)
    print("Alpaca Trader - Create Admin User")
    print("=" * 60)
    print()

    # Get user input
    username = input("Username: ").strip()
    if not username:
        print("Error: Username cannot be empty")
        return

    email = input("Email: ").strip().lower()
    if not email or "@" not in email:
        print("Error: Invalid email address")
        return

    password = getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Error: Password must be at least 8 characters")
        return

    password_confirm = getpass("Confirm password: ")
    if password != password_confirm:
        print("Error: Passwords do not match")
        return

    # Create Flask app context
    app = create_app()

    with app.app_context():
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            print(f"Error: Username '{username}' already exists")
            return

        if User.query.filter_by(email=email).first():
            print(f"Error: Email '{email}' is already registered")
            return

        # Create admin user
        user = User(
            username=username,
            email=email,
            password_hash=PasswordManager.hash_password(password),
            is_admin=True,
            is_active=True,
        )

        db.session.add(user)
        db.session.commit()

        # Create default settings
        default_settings = SettingsModel(user_id=user.id)
        db.session.add(default_settings)
        db.session.commit()

        print()
        print("✅ Admin user created successfully!")
        print()
        print(f"Username: {username}")
        print(f"Email: {email}")
        print("Role: Administrator")
        print()
        print("You can now login at: http://localhost:5000/login")


if __name__ == "__main__":
    try:
        create_admin_user()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
