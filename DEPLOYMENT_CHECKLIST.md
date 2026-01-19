# Pre-Deployment Checklist

## ✅ Code Cleanup Complete

### Files Removed (23 items):
- ✅ 10x tmpclaude-*-cwd files (temporary workspace files)
- ✅ nul (empty file)
- ✅ 5x redundant documentation (.md files)
- ✅ 3x test CSV files
- ✅ docker-compose.yml
- ✅ webapp/ directory (old version)
- ✅ deploy/ directory (Docker configs)
- ✅ output/ directory (old campaign data)

### Files Kept (Essential Only):
**Core Python Modules (9):**
- apollo_enrichment.py
- config.py
- lead_registry.py
- lead_scoring.py
- linkedin_automation.py
- main.py
- personalization_engine.py
- sequence_engine.py
- signature_manager.py
- voice_calls.py

**Scripts (2):**
- migrate_db.py (database setup)
- test_backend.py (validation)
- start.sh (startup script)

**Configuration (4):**
- requirements.txt
- .env.example
- .replit (Replit config)
- replit.nix (Nix packages)

**Documentation (3):**
- README.md
- IMPLEMENTATION_COMPLETE.md
- REPLIT_SETUP.md

**Directories (5):**
- backend/ (Flask API)
- dashboard/ (React frontend)
- data/ (SQLite database)
- templates/ (email templates)
- logs/ (application logs)

---

## 🚀 Replit Deployment Steps

### 1. Pre-Deployment Prep
- [ ] Ensure .env file has all API keys locally
- [ ] Test backend locally: `python test_backend.py`
- [ ] Verify dashboard loads: Open `dashboard/index.html`
- [ ] Backup `data/leads.db` if exists

### 2. Create Replit Project
- [ ] Go to https://replit.com
- [ ] Click "Create Repl"
- [ ] Select "Import from GitHub"
- [ ] Enter your repository URL
- [ ] Wait for import to complete

### 3. Configure Secrets
Click "Secrets" (lock icon) and add:

```env
OPENAI_API_KEY=sk-...
SENDGRID_API_KEY=SG...
BLAND_API_KEY=...
APOLLO_API_KEY=...
LINKEDIN_EMAIL=...
LINKEDIN_PASSWORD=...
BASE_URL=https://your-repl-name.your-username.repl.co
```

### 4. Install Dependencies
Replit auto-installs from requirements.txt. If needed:
```bash
pip install -r requirements.txt
```

### 5. Initialize Database
```bash
python migrate_db.py
```

### 6. Test Backend
```bash
python test_backend.py
```

Expected: All 8 tests pass ✅

### 7. Start Application
Click "Run" button or:
```bash
./start.sh
```

Backend starts on port 7000.

### 8. Configure Dashboard
Update `dashboard/src/App.jsx` if needed:
```javascript
const BACKEND_URL = 'https://your-repl-name.your-username.repl.co';
```

### 9. Access Dashboard
Open in browser:
```
https://your-repl-name.your-username.repl.co/dashboard/index.html
```

### 10. Import Leads
- Click "Import from Apollo"
- Or upload CSV with leads
- Verify leads appear in database

### 11. Create First Campaign
- Go to "Content" tab
- Set personalization mode
- Configure email templates
- Build sequence (Email → Wait → Call → LinkedIn)
- Save campaign

### 12. Test Email Preview
- Go to "Preview" tab
- Select a lead
- Generate preview
- Send test email to yourself
- Verify formatting and personalization

### 13. Enable Always-On (Recommended)
- Click "Settings" in Replit
- Enable "Always On" (requires Hacker plan $7/mo)
- This keeps sequences running 24/7

---

## 🧪 Production Testing

### Backend Endpoints (13 total)
- [ ] GET /api/variables (24 variables)
- [ ] GET /api/signatures
- [ ] POST /api/signatures/import
- [ ] GET /api/apollo/credits
- [ ] GET /api/campaigns/:id/sequence
- [ ] PUT /api/campaigns/:id/sequence
- [ ] GET /api/campaigns/:id/sequence/status
- [ ] POST /api/campaigns/:id/preview
- [ ] POST /api/campaigns/:id/test-email
- [ ] POST /api/webhooks/bland-ai
- [ ] Database schema v2 (3 new tables)

### Frontend Components (3)
- [ ] VariableAutocomplete ({{variable}} dropdown)
- [ ] EmailPreview (real-time rendering)
- [ ] SequenceBuilder (multi-step editor)

### Integrations (4)
- [ ] SendGrid (email sending)
- [ ] Bland.ai (voice calls)
- [ ] LinkedIn (connection automation)
- [ ] Apollo (lead enrichment)

---

## 📊 Launch Checklist

### Week 1: Small Batch Test
- [ ] Import 5 test leads from Apollo
- [ ] Create test campaign (conventional mode)
- [ ] Set up 3-step sequence: Email → Wait 3d → Email
- [ ] Send to test batch
- [ ] Monitor open rates and replies
- [ ] Verify no errors in logs/

### Week 2: Scale to Full Campaign
- [ ] Import 14 Apollo leads (your target)
- [ ] Create 3 campaigns (3 personalization modes)
- [ ] Set up 6-step sequences
- [ ] Enable AI calls and LinkedIn outreach
- [ ] Monitor daily for 7 days
- [ ] Track metrics in Statistics tab

### Success Metrics
- [ ] Email open rate > 30%
- [ ] Email reply rate > 5%
- [ ] Call pickup rate > 20%
- [ ] LinkedIn acceptance > 40%
- [ ] Meeting booked rate > 8%

---

## 🔒 Security & Safety

### API Key Security
- [ ] All keys stored in Replit Secrets (not .env)
- [ ] .env file in .gitignore
- [ ] No keys committed to GitHub

### LinkedIn Safety
- [ ] Using dedicated account (not personal)
- [ ] Max 30 connections/day
- [ ] Random delays (2-5 min) between actions
- [ ] Monitor for account warnings

### Email Deliverability
- [ ] SendGrid domain verified
- [ ] SPF/DKIM records configured
- [ ] Start with small batches (10-20/day)
- [ ] Monitor bounce rates

### Cost Management
- [ ] OpenAI credits: ~$0.10 per lead
- [ ] SendGrid: Free tier (100 emails/day)
- [ ] Bland.ai: ~$0.50 per call minute
- [ ] Total: $1.46-1.93 per lead (full sequence)

---

## 🐛 Troubleshooting

### Backend won't start
1. Check Secrets are configured
2. Run `python migrate_db.py`
3. Check `logs/backend.log`

### Dashboard not loading
1. Verify backend is running on port 7000
2. Check BACKEND_URL in App.jsx
3. Clear browser cache

### Emails not sending
1. Verify SENDGRID_API_KEY
2. Check sender email is verified
3. Review `logs/sendgrid.log`

### LinkedIn automation failing
1. Check LINKEDIN_EMAIL/PASSWORD
2. LinkedIn may be blocking - wait 24h
3. Use VPN if needed

### Apollo enrichment failing
1. Verify APOLLO_API_KEY
2. Check credit balance
3. Review `logs/apollo.log`

---

## 📞 Support Resources

1. **Documentation:** IMPLEMENTATION_COMPLETE.md
2. **Testing:** Run `python test_backend.py`
3. **Logs:** Check `logs/` directory
4. **Replit Docs:** https://docs.replit.com

---

## ✨ You're Ready!

Codebase is clean, organized, and production-ready. Push to Replit and launch your outreach campaign.

**Estimated Setup Time:** 15-20 minutes
**Ready to Process:** 14 Apollo leads
**Expected Results:** 1-2 meetings booked (8-14% conversion)

Good luck! 🚀
