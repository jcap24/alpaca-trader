# Testing Guide - Verify Before Deployment

Test your secure dashboard locally before deploying to production.

---

## Prerequisites

```bash
# 1. Install all dependencies
pip install -r requirements.txt

# 2. Generate security keys
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python -m alpaca_trader.security

# 3. Create .env file with keys
cp .env.example .env
# Edit .env and add your generated keys
```

---

## Local Testing Steps

### Step 1: Initialize Database (2 min)

```bash
# Create database and tables
python scripts/init_database.py
```

**Expected output:**
```
✅ Database initialized successfully!

Database location: sqlite:///alpaca_trader.db

Tables created:
  - users
  - accounts
  - watchlists
  - settings
  - audit_logs

Next step: Create an admin user
Run: python scripts/create_admin.py
```

### Step 2: Create Admin User (1 min)

```bash
# Interactive admin creation
python scripts/create_admin.py
```

**Follow prompts:**
```
Username: admin
Email: admin@example.com
Password: ********  (min 8 chars)
Confirm password: ********
```

**Expected output:**
```
✅ Admin user created successfully!

Username: admin
Email: admin@example.com
Role: Administrator

You can now login at: http://localhost:5000/login
```

### Step 3: Start Secure Dashboard (1 min)

```bash
# Start the secure dashboard
python -m alpaca_trader.main dashboard-secure
```

**Expected output:**
```
INFO:alpaca_trader:Database initialized
INFO:alpaca_trader:Secure dashboard starting at http://127.0.0.1:5000
INFO:alpaca_trader:Login at: http://127.0.0.1:5000/login
 * Serving Flask app 'dashboard_secure'
 * Running on http://127.0.0.1:5000
```

---

## Testing Checklist

### ✅ Authentication Tests

**Test 1: Login Page**
1. Open browser: `http://localhost:5000`
2. Should redirect to: `http://localhost:5000/login`
3. Verify login form displays correctly
4. Both "Login" and "Register" tabs work

**Test 2: Login with Admin**
1. Enter username: `admin`
2. Enter password: (your password)
3. Click "Login"
4. Should redirect to dashboard
5. Should see trading dashboard with empty data

**Test 3: Logout**
1. Click browser back (or navigate to `/api/auth/logout`)
2. Make POST request to `/api/auth/logout`
3. Should be logged out
4. Navigating to `/` should redirect to `/login`

**Test 4: Invalid Login**
1. Try wrong username
2. Try wrong password
3. Should show error: "Invalid credentials"
4. Should not log in

**Test 5: Registration**
1. Click "Register" tab
2. Enter:
   - Username: `testuser`
   - Email: `test@example.com`
   - Password: `password123`
   - Confirm: `password123`
3. Click "Create Account"
4. Should show success message
5. Should switch to login tab
6. Login with new credentials

### ✅ Trading Account Tests

**Test 6: Add Trading Account**
1. Login to dashboard
2. Scroll to "Trading Accounts" section
3. Click "+ Add Account"
4. Enter:
   - Account Name: `Paper Trading`
   - API Key: (your Alpaca paper API key)
   - Secret Key: (your Alpaca paper secret key)
   - Paper Trading: ✓ Checked
5. Click "Add"
6. Should show success message
7. Account should appear in table
8. Should be marked as "Active" (first account)

**Test 7: API Key Encryption**
1. Check database directly:
   ```bash
   python -c "from alpaca_trader.models import db, Account; from alpaca_trader.dashboard_secure import create_app; app = create_app(); app.app_context().push(); acc = Account.query.first(); print('Encrypted:', acc.api_key_encrypted[:50], '...')"
   ```
2. Encrypted keys should be long base64 strings
3. Should NOT show plain API keys

**Test 8: Switch Active Account**
1. Add second account
2. Click "Activate" on second account
3. First account should become inactive
4. Second account should become active
5. API calls should use second account

**Test 9: Edit Account**
1. Click "Edit" on an account
2. Change API keys
3. Click "Update"
4. Should save successfully

**Test 10: Delete Account**
1. Click "Delete" on an account
2. Confirm deletion
3. Account should be removed
4. If it was active, another should become active

### ✅ Watchlist Tests

**Test 11: Add Symbol**
1. Scroll to "Watchlist Management"
2. Click "+ Add Symbol"
3. Enter symbol: `AAPL`
4. Click "Add"
5. Should validate ticker with Alpaca
6. Should auto-fill company name: "Apple Inc."
7. Should appear in watchlist table

**Test 12: Invalid Symbol**
1. Try adding: `INVALID_TICKER_12345`
2. Should show error: "Symbol not found"
3. Should not be added to watchlist

**Test 13: Duplicate Symbol**
1. Try adding `AAPL` again
2. Should show error: "Symbol already in watchlist"

**Test 14: Remove Symbol**
1. Click "Remove" next to a symbol
2. Confirm removal
3. Symbol should disappear from list

### ✅ Signals Tests

**Test 15: View Signals**
1. Add symbols to watchlist: `AAPL`, `GOOGL`, `MSFT`
2. Scroll to "Live Signals" section
3. Should display signals for all symbols
4. Each row should show:
   - Symbol
   - Company name
   - Current price
   - Signal (Buy/Sell/Hold)
   - Strength percentage
   - Indicator details

**Test 16: Empty Watchlist**
1. Remove all symbols from watchlist
2. Signals section should show: "No signals available"

### ✅ Indicator Settings Tests

**Test 17: Toggle Indicators**
1. Scroll to "Technical Indicators"
2. Toggle RSI off
3. Toggle SMA off
4. Signals should update
5. Toggle back on
6. Signals should recalculate

**Test 18: Settings Persistence**
1. Toggle indicators
2. Logout
3. Login again
4. Indicator settings should be preserved

### ✅ Portfolio Tests

**Test 19: Account Summary**
1. Top cards should show:
   - Equity
   - Cash
   - Buying Power
   - Portfolio Value
2. Values should match Alpaca account

**Test 20: Open Positions**
1. If you have open positions in Alpaca
2. Should display in "Open Positions" table
3. Should show P&L correctly

**Test 21: Trade History**
1. If you have past trades
2. Should display in "Trade History" table
3. Should show most recent 50 orders

### ✅ Multi-User Tests

**Test 22: User Isolation**
1. Create second user
2. Login as second user
3. Should NOT see first user's:
   - Trading accounts
   - Watchlist
   - Settings
4. Data should be completely isolated

**Test 23: Concurrent Users**
1. Open two browsers (or incognito)
2. Login as different users
3. Both should work simultaneously
4. Changes in one should not affect the other

### ✅ Security Tests

**Test 24: Protected Routes**
1. Logout
2. Try accessing: `http://localhost:5000/`
3. Should redirect to login
4. Try accessing: `http://localhost:5000/api/account`
5. Should return 401 Unauthorized

**Test 25: CSRF Protection**
1. Try making POST request without CSRF token
2. Should be rejected (if CSRF is enforced on that endpoint)

**Test 26: Rate Limiting**
1. Try login 20 times rapidly with wrong password
2. Should eventually be rate limited
3. Wait 1 minute, should work again

---

## Common Issues & Solutions

### Issue: `ModuleNotFoundError: No module named 'cryptography'`

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: `ValueError: ENCRYPTION_KEY environment variable not set`

**Solution:**
```bash
# Generate key
python -m alpaca_trader.security

# Add to .env file
echo "ENCRYPTION_KEY=<generated-key>" >> .env
```

### Issue: `SECRET_KEY not set`

**Solution:**
```bash
# Generate key
python -c "import secrets; print(secrets.token_hex(32))"

# Add to .env file
echo "SECRET_KEY=<generated-key>" >> .env
```

### Issue: Database tables don't exist

**Solution:**
```bash
# Reinitialize database
rm alpaca_trader.db  # Delete old database
python scripts/init_database.py
python scripts/create_admin.py
```

### Issue: Can't login after creating user

**Solution:**
- Verify user was created:
  ```bash
  python -c "from alpaca_trader.models import db, User; from alpaca_trader.dashboard_secure import create_app; app = create_app(); app.app_context().push(); print(User.query.all())"
  ```
- Check password is correct
- Try creating new user

### Issue: Signals not showing

**Possible causes:**
1. No active trading account → Add account
2. Empty watchlist → Add symbols
3. Invalid API keys → Check keys are correct
4. All indicators disabled → Enable at least one

### Issue: "No active trading account" error

**Solution:**
1. Go to "Trading Accounts" section
2. Add an account with valid API keys
3. Ensure it's marked as "Active"

---

## Performance Tests

### Test 27: Page Load Speed
- Dashboard should load in < 2 seconds
- API calls should complete in < 1 second
- Charts should render smoothly

### Test 28: Large Watchlist
- Add 20+ symbols
- Signals should still load within 5 seconds
- UI should remain responsive

---

## Production Readiness Checklist

Before deploying to production:

- [ ] All local tests pass
- [ ] SECRET_KEY is strong and secure
- [ ] ENCRYPTION_KEY is strong and secure
- [ ] Admin password is strong
- [ ] 2FA is enabled for admin (optional but recommended)
- [ ] Database is PostgreSQL (not SQLite)
- [ ] FLASK_ENV=production in environment
- [ ] Debug mode is OFF
- [ ] All sensitive data is in .env (not committed)
- [ ] .gitignore includes .env and *.db
- [ ] Backup strategy is in place

---

## Next Steps

Once all tests pass:

1. **Review DEPLOYMENT.md** for deployment instructions
2. **Follow QUICKSTART_DEPLOY.md** for step-by-step deployment
3. **Deploy to Render** (or your chosen platform)
4. **Run tests again** on production
5. **Monitor logs** for any errors
6. **Set up backups** and monitoring

---

## Test Summary

| Category | Tests | Status |
|----------|-------|--------|
| Authentication | 5 tests | ⬜ Not Run |
| Trading Accounts | 5 tests | ⬜ Not Run |
| Watchlist | 4 tests | ⬜ Not Run |
| Signals | 2 tests | ⬜ Not Run |
| Indicators | 2 tests | ⬜ Not Run |
| Portfolio | 3 tests | ⬜ Not Run |
| Multi-User | 2 tests | ⬜ Not Run |
| Security | 3 tests | ⬜ Not Run |
| Performance | 2 tests | ⬜ Not Run |
| **Total** | **28 tests** | ⬜ **0% Complete** |

---

**Ready to test? Let's go!** 🚀

Start with: `python scripts/init_database.py`
