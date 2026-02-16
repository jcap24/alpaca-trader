# Upgrade Guide: Adding Production-Ready Security

This guide walks you through upgrading your Alpaca Trader dashboard to a secure, multi-user production system.

## Overview

The upgrade adds:
- ✅ User authentication & authorization
- ✅ Encrypted API key storage
- ✅ CSRF protection
- ✅ Rate limiting
- ✅ Database storage (SQLAlchemy)
- ✅ Multi-user support
- ✅ Two-factor authentication (2FA)
- ✅ Audit logging
- ✅ Security headers
- ✅ Production WSGI server (Gunicorn)

## Prerequisites

```bash
# Install new dependencies
pip install -r requirements.txt
```

## Step 1: Environment Configuration

Create or update your `.env` file:

```bash
# Security
SECRET_KEY=your-secret-key-here-generate-with-python-secrets
ENCRYPTION_KEY=your-encryption-key-here

# Database
DATABASE_URL=sqlite:///alpaca_trader.db
# For PostgreSQL: postgresql://user:pass@localhost/alpaca_trader

# Flask
FLASK_ENV=production  # or 'development'
FLASK_APP=alpaca_trader.dashboard_secure:create_app

# Optional: For production
GUNICORN_WORKERS=4
GUNICORN_BIND=0.0.0.0:5000
```

### Generate Keys

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Generate ENCRYPTION_KEY
python -m alpaca_trader.security
```

## Step 2: Database Setup

### Initialize Database

```bash
# Create database and tables
python -c "from alpaca_trader.dashboard_secure import create_app; from alpaca_trader.models import db; app = create_app(); app.app_context().push(); db.create_all(); print('Database created!')"
```

### Migrate Existing Data (Optional)

If you have existing data in YAML files, run the migration script:

```bash
python scripts/migrate_yaml_to_db.py
```

## Step 3: Create Admin User

```bash
python scripts/create_admin.py
```

Or through the UI:
1. Start the app: `python -m alpaca_trader.main dashboard-secure`
2. Navigate to `/login`
3. Click "Register" tab
4. First user becomes admin automatically

## Step 4: Update Your Startup

### Development

```bash
# Old way (insecure)
python -m alpaca_trader.main dashboard

# New way (secure)
python -m alpaca_trader.main dashboard-secure
```

### Production

```bash
# Using Gunicorn
gunicorn -c gunicorn_config.py "alpaca_trader.dashboard_secure:create_app()"
```

## Step 5: Security Checklist

Before deploying to production:

- [ ] Set strong `SECRET_KEY` and `ENCRYPTION_KEY` in `.env`
- [ ] Set `FLASK_ENV=production` in `.env`
- [ ] Use PostgreSQL instead of SQLite for production
- [ ] Enable HTTPS (use nginx/Cloudflare)
- [ ] Set up firewall rules
- [ ] Configure backup strategy for database
- [ ] Enable 2FA for admin accounts
- [ ] Review audit logs regularly
- [ ] Set up monitoring/alerting

## Step 6: User Management

### Creating Users

1. **Via Web UI**: Navigate to `/login` → Register tab
2. **Via Script**: `python scripts/create_user.py`

### Managing Accounts

Each user can manage their own trading accounts:
1. Login to dashboard
2. Navigate to "Trading Accounts" section
3. Click "+ Add Account"
4. Enter Alpaca API credentials
5. Set as active account

### Enabling 2FA (Recommended)

1. Login to dashboard
2. Navigate to Profile → Security
3. Click "Enable Two-Factor Authentication"
4. Scan QR code with authenticator app
5. Enter verification code

## Migration Timeline

### Phase 1: Basic Security (Week 1)
- [x] Install dependencies
- [x] Set up database
- [ ] Create admin user
- [ ] Migrate API keys to encrypted storage
- [ ] Test authentication flow

### Phase 2: Multi-User (Week 2)
- [ ] Migrate existing users (if any)
- [ ] Set up user isolation
- [ ] Test multi-user scenarios
- [ ] Configure rate limiting

### Phase 3: Production Deploy (Week 3)
- [ ] Set up production database (PostgreSQL)
- [ ] Configure Gunicorn
- [ ] Set up nginx reverse proxy
- [ ] Enable HTTPS
- [ ] Configure monitoring
- [ ] Perform security audit

## Backward Compatibility

The old `dashboard.py` remains available for local development:

```bash
# Old insecure version (local only)
python -m alpaca_trader.main dashboard --no-scheduler

# New secure version
python -m alpaca_trader.main dashboard-secure
```

## Troubleshooting

### Database Errors

```bash
# Reset database (WARNING: Deletes all data)
rm alpaca_trader.db
python -c "from alpaca_trader.dashboard_secure import create_app; from alpaca_trader.models import db; app = create_app(); app.app_context().push(); db.create_all()"
```

### CSRF Errors

If you get CSRF errors when using the API:
- For browser requests: Ensure templates include `{{ csrf_token() }}`
- For API requests: Either disable CSRF for specific endpoints or include token

### Encryption Errors

If you get decryption errors:
- Ensure `ENCRYPTION_KEY` hasn't changed
- If keys changed, you'll need to re-encrypt all stored API keys

## API Changes

### Authentication Required

All API endpoints now require authentication:

```javascript
// Old way (no auth)
fetch('/api/account')

// New way (session-based auth)
// Login first, then:
fetch('/api/account', {
    credentials: 'include'  // Include session cookie
})
```

### Rate Limits

Default limits:
- Authentication endpoints: 5-10 requests/minute
- API endpoints: 200/day, 50/hour
- Admin endpoints: 100/day, 20/hour

Customize in `dashboard_secure.py`:

```python
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)
```

## Security Best Practices

### API Key Storage

- **Never** commit `.env` files
- **Never** store API keys in code
- **Always** use encrypted storage for sensitive data

### Password Policy

- Minimum 8 characters
- Use password managers
- Enable 2FA for all users
- Rotate passwords quarterly

### Monitoring

Monitor these audit log events:
- `login_failed` - Potential brute force attacks
- `2fa_failed` - Potential account compromise
- `account_created` - Unauthorized access
- `account_deleted` - Data loss risk

Query audit logs:

```python
from alpaca_trader.models import AuditLog
recent_logins = AuditLog.query.filter_by(action='login').order_by(AuditLog.timestamp.desc()).limit(10).all()
```

## Support

For issues or questions:
1. Check the logs: `logs/alpaca_trader.log`
2. Review audit logs in database
3. Open GitHub issue: https://github.com/jcap24/alpaca-trader/issues

## Next Steps

After completing the upgrade:
1. Review security checklist
2. Perform penetration testing
3. Set up automated backups
4. Configure monitoring/alerting
5. Train users on security features
6. Document your deployment

---

**Important**: This upgrade changes how the application handles sensitive data. Plan for downtime during migration and thoroughly test in a staging environment before deploying to production.
