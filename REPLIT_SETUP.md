# Replit Deployment Guide

## Quick Setup (5 Minutes)

### 1. Create Replit Project
1. Go to [Replit](https://replit.com)
2. Click "Create Repl"
3. Choose "Import from GitHub"
4. Import this repository

### 2. Configure Environment Variables
Click on "Secrets" (lock icon) in Replit sidebar and add:

```
OPENAI_API_KEY=your_openai_api_key
SENDGRID_API_KEY=your_sendgrid_api_key
BLAND_API_KEY=your_bland_api_key
LINKEDIN_EMAIL=your_linkedin_email
LINKEDIN_PASSWORD=your_linkedin_password
APOLLO_API_KEY=your_apollo_api_key
BASE_URL=https://your-repl-name.your-username.repl.co
```

### 3. Install Dependencies
Replit will automatically install from `requirements.txt` on first run.

If manual installation needed:
```bash
pip install -r requirements.txt
```

### 4. Run Database Migration
```bash
python migrate_db.py
```

### 5. Start the Application
Click the "Run" button or:
```bash
./start.sh
```

Backend will start on port 7000.

### 6. Test the Backend
```bash
python test_backend.py
```

### 7. Access Dashboard
Open the dashboard:
- In Replit webview: Navigate to `/dashboard/index.html`
- Or open `dashboard/index.html` in a new browser tab
- Update API URL in dashboard if needed

## Replit-Specific Notes

### Port Configuration
Replit automatically assigns a public URL. Your backend will be accessible at:
```
https://your-repl-name.your-username.repl.co
```

### Always-On
For production use:
1. Click "Settings" in Replit
2. Enable "Always On" (requires Hacker plan)
3. This keeps your outreach sequences running 24/7

### Database Persistence
The `data/` directory persists across Repl restarts. Your leads and campaigns are safe.

### LinkedIn Automation
LinkedIn automation (Selenium) works on Replit with Chrome/Chromedriver installed via `replit.nix`.

Note: LinkedIn may detect automation. Use carefully:
- Keep daily connection requests under 30
- Add random delays between actions
- Use a dedicated LinkedIn account

### File Storage
Outlook signatures will be imported from:
- Replit: Use upload feature to add signature files to `data/signatures/`

### Scheduling Sequences
For automated sequence execution:
1. Keep Replit "Always On"
2. Or use Replit's cron jobs feature
3. Or integrate with external schedulers (cron-job.org)

## Cost Breakdown on Replit

**Replit Plans:**
- Starter (Free): Good for testing, limited uptime
- Hacker ($7/mo): Always-on, better for production
- Pro ($20/mo): More resources, faster execution

**Recommended Setup:**
- Hacker plan ($7/mo) for reliable outreach
- Total monthly cost: $7 Replit + API costs

## Troubleshooting

### Backend Won't Start
1. Check if all environment variables are set in Secrets
2. Run `python migrate_db.py` manually
3. Check `logs/` directory for error messages

### Dashboard Not Loading
1. Update `BACKEND_URL` in `dashboard/src/App.jsx`
2. Rebuild dashboard: `cd dashboard && npm run build`

### LinkedIn Automation Failing
1. Verify Chrome/Chromedriver are installed
2. Check `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` in Secrets
3. LinkedIn may be blocking automated access - use VPN or wait 24 hours

### Apollo Enrichment Failing
1. Verify `APOLLO_API_KEY` in Secrets
2. Check credit balance at Apollo.io dashboard
3. Review `logs/apollo.log` for errors

## Next Steps

1. Import your Apollo leads: `python apollo_enrichment.py`
2. Create your first campaign in the dashboard
3. Set up sequences (Email → Call → LinkedIn)
4. Test with small batch (5 leads)
5. Monitor results in Statistics tab
6. Scale to full campaign

## Support

For issues:
1. Check `logs/` directory
2. Run `python test_backend.py` to diagnose
3. Review `IMPLEMENTATION_COMPLETE.md` for detailed docs
