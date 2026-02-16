"""Initialize the database with tables."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alpaca_trader.dashboard_secure import create_app
from alpaca_trader.models import db


def init_database():
    """Create all database tables."""
    print("Initializing database...")

    app = create_app()

    with app.app_context():
        # Create all tables
        db.create_all()

        print("✅ Database initialized successfully!")
        print()
        print(f"Database location: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print()
        print("Tables created:")
        print("  - users")
        print("  - accounts")
        print("  - watchlists")
        print("  - settings")
        print("  - audit_logs")
        print()
        print("Next step: Create an admin user")
        print("Run: python scripts/create_admin.py")


if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
