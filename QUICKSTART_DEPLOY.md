# Quick Start: Get Online in 30 Minutes ⚡

**Fastest path to production deployment of your Alpaca Trader dashboard.**

---

## ⚠️ Prerequisites

Before you can deploy, you need to complete the core functionality:

### Current Status
- ✅ Security infrastructure complete (encryption, auth, models)
- ✅ Login/register UI complete
- ✅ Database models complete
- 🟡 **`dashboard_secure.py` needs completion (~2-3 hours)**

### Option 1: Deploy Simple Version (Quick - 30 min)

Use a basic auth wrapper around existing `dashboard.py`:

```bash
# I can help you create this wrapper if you want the fastest path
```

**Pros:** Get online immediately
**Cons:** No multi-user support, basic security only

### Option 2: Complete Secure Version First (Recommended - 3-4 hours)

Finish `dashboard_secure.py` before deploying:

1. Port remaining API endpoints
2. Add user isolation
3. Test locally
4. Then deploy

**Pros:** Full security from day 1
**Cons:** Takes longer

---

## 🚀 Deployment Steps (After Code is Complete)

### Step 1: Prepare Repository (5 min)

```bash
# 1. Commit all changes
git add .
git commit -m "Ready for deployment"
git push origin main

# 2. Verify files exist:
ls render.yaml        # ✓
ls Procfile          # ✓
ls runtime.txt       # ✓
ls requirements.txt  # ✓
ls gunicorn_config.py # ✓
```

### Step 2: Sign Up for Render (2 min)

1. Go to [render.com](https://render.com)
2. Click "Get Started"
3. Sign up with GitHub
4. Authorize Render to access repositories

### Step 3: One-Click Deploy (3 min)

**Option A: Blueprint Deploy (Easiest)**

1. Click this button: [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
2. Select your repository
3. Render reads `render.yaml` and creates everything automatically
4. Done!

**Option B: Manual Deploy**

1. Dashboard → "New +" → "Blueprint"
2. Connect GitHub repository
3. Render detects `render.yaml`
4. Click "Apply"
5. Done!

### Step 4: Generate Security Keys (2 min)

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# Copy output

# Generate ENCRYPTION_KEY
python -m alpaca_trader.security
# Copy output
```

### Step 5: Set Environment Variables (3 min)

In Render dashboard:

1. Click on your web service
2. Go to "Environment" tab
3. Add these variables:

```
SECRET_KEY=<paste from Step 4>
ENCRYPTION_KEY=<paste from Step 4>
FLASK_ENV=production
```

4. Click "Save Changes"
5. Service will auto-redeploy

### Step 6: Initialize Database (5 min)

After deployment completes:

1. Go to your web service in Render
2. Click "Shell" tab
3. Run these commands:

```bash
# Create database tables
python scripts/init_database.py

# Create admin user (interactive)
python scripts/create_admin.py
# Enter username, email, password when prompted
```

### Step 7: Test Your App! (5 min)

1. Click "Open App" or visit your URL: `https://your-app.onrender.com`
2. Navigate to `/login`
3. Login with admin credentials
4. Add a trading account in "Trading Accounts" section
5. Add symbols to watchlist
6. Verify everything works!

---

## 📋 Pre-Flight Checklist

Before deploying, verify:

- [ ] Code is complete and tested locally
- [ ] All files committed to Git
- [ ] `requirements.txt` is up to date
- [ ] `.env.example` exists (for documentation)
- [ ] `.env` is in `.gitignore` (don't commit secrets!)
- [ ] Database models are finalized
- [ ] Security keys generated

---

## 🔧 Troubleshooting

### Build Fails

**Error:** `No module named 'alpaca_trader'`
```bash
# Solution: Verify requirements.txt has all dependencies
pip freeze > requirements.txt
git commit -am "Update requirements"
git push
```

### App Won't Start

**Error:** `SECRET_KEY not set`
```bash
# Solution: Set environment variables in Render dashboard
# See Step 5 above
```

### Can't Access /login

**Error:** `404 Not Found`
```bash
# Solution: Verify dashboard_secure.py has route defined:
@app.route("/login")
def login_page():
    return render_template("login.html")
```

### Database Tables Missing

**Error:** `relation "users" does not exist`
```bash
# Solution: Run init_database.py in Shell
python scripts/init_database.py
```

---

## 💰 Costs

### Render (Recommended)

**Free Tier:**
- Web App: Free (sleeps after 15 min inactivity)
- PostgreSQL: Free for 90 days, then $7/month
- **Total: $0** (first 90 days), then **$7/month**

**Paid Tier (No Sleep):**
- Web App: $7/month
- PostgreSQL: $7/month
- **Total: $14/month**

### Railway (Alternative)

- **$5/month** flat fee
- Includes everything (web + database)
- Fair usage limits

---

## 🎯 Post-Deployment

After going live:

1. **Test Everything**
   - Login/logout
   - Add trading accounts
   - Add watchlist symbols
   - View signals
   - Check portfolio data

2. **Set Up Monitoring**
   - Render has built-in uptime monitoring
   - Configure email alerts

3. **Custom Domain (Optional)**
   - Add your domain in Render settings
   - Point DNS to Render
   - SSL auto-configured

4. **Invite Users**
   - Share `/login` URL
   - Users can register
   - Admin can manage via database

---

## 📞 Next Steps

1. **Complete the code** (if using Option 2)
   - Finish `dashboard_secure.py`
   - Test locally

2. **Deploy** (follow steps above)
   - Should take ~30 minutes once code is ready

3. **Go live!**
   - Share with users
   - Monitor performance
   - Iterate and improve

---

## 🆘 Need Help?

If you get stuck:

1. Check [DEPLOYMENT.md](DEPLOYMENT.md) for detailed guide
2. Review [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for current progress
3. Check Render logs: Dashboard → Logs tab
4. Test locally with production settings

---

## ⏱️ Timeline Summary

| Task | Time | Status |
|------|------|--------|
| Complete code | 3-4 hours | 🟡 Pending |
| Prepare repository | 5 min | ✅ Ready |
| Sign up for Render | 2 min | - |
| Deploy to Render | 3 min | - |
| Set environment vars | 3 min | - |
| Initialize database | 5 min | - |
| Test deployment | 5 min | - |
| **Total** | **~4 hours** | - |

**If using Simple Version (Option 1): ~1 hour total**

---

## 🎉 That's It!

You'll have a production-ready, secure trading dashboard with:
- ✅ HTTPS encryption
- ✅ User authentication
- ✅ Encrypted API keys
- ✅ PostgreSQL database
- ✅ Auto-scaling
- ✅ Automatic backups
- ✅ Zero DevOps required

**Ready to deploy? Let's go!** 🚀
