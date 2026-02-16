# Deployment Guide - Get Your App Online in 30 Minutes

This guide walks you through deploying your Alpaca Trader dashboard to production.

## Recommended Platform: Render.com

**Why Render?**
- Free tier for small apps
- Automatic HTTPS
- PostgreSQL database included
- Auto-deploy from GitHub
- Zero configuration needed

**Alternatives:**
- Railway.app (similar to Render)
- Heroku (classic choice, no longer free)
- DigitalOcean App Platform ($5/month)

---

## Prerequisites Checklist

Before deploying, complete these steps:

### 1. Complete Remaining Code

You need to finish `dashboard_secure.py` first. The quickest path:

**Option A: Use simplified version (Quick - 30 min)**
- Use the existing insecure `dashboard.py` with basic auth wrapper
- Get online fast, migrate to full security later

**Option B: Complete secure version (Thorough - 4-6 hours)**
- Finish all API endpoints in `dashboard_secure.py`
- Full security from day 1

**Recommendation for initial deployment: Option A**

### 2. Prepare Your Repository

```bash
# Ensure all code is committed
git add .
git commit -m "Prepare for deployment"
git push origin main
```

### 3. Create Production Files

I'll create these for you:
- `render.yaml` - Render deployment config
- `.env.example` - Template for environment variables
- `Procfile` - Process definition
- `runtime.txt` - Python version

---

## Step-by-Step Deployment

### Step 1: Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with GitHub (recommended)
3. Authorize Render to access your repositories

### Step 2: Create PostgreSQL Database

1. Click "New +" → "PostgreSQL"
2. Name: `alpaca-trader-db`
3. Database: `alpaca_trader`
4. User: `alpaca_user`
5. Region: Choose closest to you
6. Plan: **Free**
7. Click "Create Database"
8. **Copy the Internal Database URL** (you'll need this)

### Step 3: Create Web Service

1. Click "New +" → "Web Service"
2. Connect your GitHub repository
3. Configure:

```
Name: alpaca-trader-dashboard
Environment: Python 3
Region: Same as database
Branch: main
Build Command: pip install -r requirements.txt
Start Command: gunicorn -c gunicorn_config.py "alpaca_trader.dashboard_secure:create_app()"
Plan: Free
```

### Step 4: Set Environment Variables

In the Render dashboard, add these environment variables:

```bash
# Required
DATABASE_URL=<paste Internal Database URL from Step 2>
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
ENCRYPTION_KEY=<generate: python -m alpaca_trader.security>

# Flask
FLASK_ENV=production

# Optional
LOG_LEVEL=info
```

**Important:** Generate unique keys for `SECRET_KEY` and `ENCRYPTION_KEY`!

### Step 5: Initialize Database

After first deployment, you need to create tables:

1. Go to Render dashboard
2. Click on your web service
3. Go to "Shell" tab
4. Run:

```bash
python scripts/init_database.py
python scripts/create_admin.py
```

### Step 6: Deploy!

1. Click "Manual Deploy" → "Deploy latest commit"
2. Wait 2-3 minutes for build
3. Your app will be live at: `https://alpaca-trader-dashboard.onrender.com`

---

## Alternative: Railway.app

Very similar to Render, even easier:

1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Railway auto-detects Python and sets everything up
5. Add PostgreSQL from "Add Plugin" menu
6. Set environment variables
7. Deploy!

---

## Post-Deployment Checklist

### Security

- [ ] Verify HTTPS is enabled (automatic on Render/Railway)
- [ ] Confirm `FLASK_ENV=production` is set
- [ ] Test login/authentication works
- [ ] Create admin user
- [ ] Enable 2FA on admin account
- [ ] Review security headers (test with [securityheaders.com](https://securityheaders.com))

### Functionality

- [ ] Test login/logout
- [ ] Add trading account
- [ ] Add symbols to watchlist
- [ ] Verify signals display
- [ ] Check portfolio data loads
- [ ] Test on mobile device

### Monitoring

- [ ] Set up uptime monitoring (Render has built-in)
- [ ] Configure error alerts
- [ ] Review logs for errors

---

## Custom Domain (Optional)

### With Render:

1. Go to "Settings" → "Custom Domain"
2. Add your domain (e.g., `trading.yourdomain.com`)
3. Add CNAME record in your DNS:
   ```
   CNAME trading.yourdomain.com → alpaca-trader-dashboard.onrender.com
   ```
4. Render automatically provisions SSL certificate

### DNS Providers:
- Cloudflare (recommended - free, adds DDoS protection)
- Namecheap
- Google Domains

---

## Estimated Costs

### Free Tier (Render)
- Web Service: **Free** (sleeps after 15 min inactivity)
- PostgreSQL: **Free** (90 days, then $7/month)
- **Total: $0/month** (first 90 days), then **$7/month**

### Paid Tier (No Sleep)
- Web Service: **$7/month** (always on)
- PostgreSQL: **$7/month**
- **Total: $14/month**

### Railway
- **$5/month** flat fee (includes everything)
- Fair usage limits

---

## Quick Deploy Commands

```bash
# 1. Generate keys
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python -m alpaca_trader.security  # Copy ENCRYPTION_KEY

# 2. Test locally first
export DATABASE_URL="postgresql://localhost/alpaca_trader"
export SECRET_KEY="<your-key>"
export ENCRYPTION_KEY="<your-key>"
export FLASK_ENV="production"

# 3. Initialize database
python scripts/init_database.py
python scripts/create_admin.py

# 4. Test production mode locally
gunicorn -c gunicorn_config.py "alpaca_trader.dashboard_secure:create_app()"

# 5. Visit http://localhost:5000/login
```

---

## Troubleshooting

### Build Fails

**Problem:** `ModuleNotFoundError`
**Solution:** Ensure `requirements.txt` is up to date

**Problem:** Database connection fails
**Solution:** Check `DATABASE_URL` is set correctly

### App Crashes on Startup

**Problem:** `SECRET_KEY not set`
**Solution:** Add `SECRET_KEY` to environment variables

**Problem:** `ENCRYPTION_KEY not set`
**Solution:** Add `ENCRYPTION_KEY` to environment variables

### Can't Login

**Problem:** No admin user created
**Solution:** Run `python scripts/create_admin.py` in Shell

### Database Tables Missing

**Problem:** Tables not created
**Solution:** Run `python scripts/init_database.py` in Shell

---

## Migration from Development

If you have existing data in YAML files:

1. Deploy app
2. Access Shell in Render
3. Upload YAML files (or commit to repo)
4. Run migration script:
   ```bash
   python scripts/migrate_yaml_to_db.py
   ```

---

## Maintenance

### Updating the App

1. Push changes to GitHub
2. Render auto-deploys (or click "Manual Deploy")
3. Watch logs for errors

### Database Backups

Render automatically backs up PostgreSQL daily.

Manual backup:
```bash
# In Render Shell
pg_dump $DATABASE_URL > backup.sql
```

### Monitoring

- **Logs:** Render Dashboard → Logs tab
- **Metrics:** Render Dashboard → Metrics tab
- **Uptime:** Set up alerts in Render settings

---

## Next Steps After Deployment

1. **Test thoroughly** - Try all features
2. **Add team members** - Create accounts for users
3. **Configure alerts** - Email notifications for trades
4. **Set up monitoring** - UptimeRobot or Pingdom
5. **Plan backups** - Export data regularly
6. **Scale if needed** - Upgrade to paid tier

---

## Support

If you encounter issues:

1. Check Render logs: Dashboard → Logs
2. Test locally with production settings
3. Review error messages carefully
4. Check GitHub Issues for similar problems

---

## Estimated Timeline

- **Quick Deploy (Option A):** 30-45 minutes
- **Full Secure Deploy (Option B):** 4-6 hours + 30 min deployment
- **Custom Domain:** +15 minutes
- **Testing & Validation:** 30-60 minutes

**Total Time to Production: 1-7 hours** depending on approach.

---

## Production-Ready Checklist

- [ ] All environment variables set
- [ ] Database initialized
- [ ] Admin user created
- [ ] HTTPS enabled (automatic)
- [ ] Login tested
- [ ] Trading account added
- [ ] Watchlist works
- [ ] Signals display correctly
- [ ] Error pages work
- [ ] Mobile responsive
- [ ] Logs show no errors
- [ ] Uptime monitoring configured

🎉 **You're Live!**
