# Leadfeeder Integration Setup Guide

This guide explains how to integrate Leadfeeder's free tier with your personalized outreach platform to identify website visitors before the 7-day data expiration.

## What is Leadfeeder?

Leadfeeder identifies companies visiting your website using IP-to-company matching. The **free tier** provides:
- ✅ 7 days of visitor data history
- ✅ Company identification
- ✅ Page views and visit details
- ❌ Limited to 100 companies/month
- ❌ Data expires after 7 days

**Our Solution**: Automatically scrape Leadfeeder data daily before it expires, then enrich with Apollo for contact details.

## Prerequisites

1. **Leadfeeder Free Account** - Sign up at https://www.leadfeeder.com
2. **Leadfeeder Tracking Script** - Installed on your WordPress site
3. **Python Dependencies** - Selenium and Chrome driver (already in requirements.txt)

## Step 1: Create Leadfeeder Account

1. Go to https://www.leadfeeder.com
2. Sign up for a **free account**
3. Add your website domain
4. Install their tracking script on WordPress (similar to our visitor tracking)

### Install Leadfeeder Tracking on WordPress

Leadfeeder will give you a tracking script like this:

```html
<script>
(function(){window.ldfdr=window.ldfdr||{};(function(d,s,ss,fs){
fs=d.getElementsByTagName(s)[0];
function ce(src){var cs=d.createElement(s);cs.src=src;
setTimeout(function(){fs.parentNode.insertBefore(cs,fs)},1);};
ce(ss);
})(document,'script','https://lftracker.leadfeeder.com/lftracker_v1_YOUR_ID.js');
})();
</script>
```

Add this to your WordPress **header** (same way you'll add our tracking script).

**Note**: You can run both tracking scripts simultaneously - Leadfeeder for their data, ours for our own tracking.

## Step 2: Configure Credentials in .env

Add your Leadfeeder login credentials to your `.env` file:

```env
# Leadfeeder Integration (Optional)
LEADFEEDER_EMAIL=your-email@example.com
LEADFEEDER_PASSWORD=your-password
```

**Security Note**: Use a dedicated password for Leadfeeder, not your personal password.

## Step 3: How It Works Automatically

Once configured, the system automatically:

1. **Daily Scrape** (2 AM UTC) - Logs into Leadfeeder, scrapes visitor data
2. **Store Locally** - Saves company data in your database
3. **Data Reconciliation** (Every 2 hours) - Merges Leadfeeder data with your DIY tracking
4. **Confidence Scoring** - Ranks companies based on data sources
5. **Apollo Enrichment** - Find contacts at identified companies (on-demand)

### Automated Jobs

Your scheduler runs these jobs:

| Job | Frequency | Purpose |
|-----|-----------|---------|
| **Leadfeeder Scrape** | Daily at 2 AM UTC | Capture visitor data before 7-day expiration |
| **IP Resolution** | Every hour | Resolve IPs from your DIY tracking |
| **Data Reconciliation** | Every 2 hours | Merge all data sources |
| **Data Cleanup** | Daily at 4 AM UTC | Remove old expired data |

## Step 4: Test the Integration

### Manual Test (Before Deployment)

Run a one-time scrape to test your credentials:

```python
from leadfeeder_scraper import scrape_leadfeeder

result = scrape_leadfeeder()
print(result)
# {'success': True, 'companies_scraped': 23, 'companies_stored': 23}
```

### Check Status via API

```bash
# Check if Leadfeeder is configured
curl http://localhost:7000/api/integrations/leadfeeder/status
```

Response:
```json
{
  "configured": true,
  "status": {
    "status": "active",
    "last_sync_at": "2026-01-30T12:00:00Z",
    "error_message": null
  },
  "active_companies": 47,
  "expiring_soon": 12
}
```

### Manual Trigger (For Testing)

```bash
# Trigger Leadfeeder scrape immediately
curl -X POST http://localhost:7000/api/integrations/leadfeeder/scrape
```

## Step 5: View Identified Visitors

### In Dashboard
Visit the **Analytics** tab to see:
- Combined visitor data (your tracking + Leadfeeder)
- Company names, domains, visit counts
- Confidence scores (higher when both sources agree)

### Via API
```bash
# List all identified visitors
curl http://localhost:7000/api/visitors

# Filter by Leadfeeder source
curl "http://localhost:7000/api/visitors?source=leadfeeder"

# High confidence only (data from multiple sources)
curl "http://localhost:7000/api/visitors?min_confidence=0.8"
```

### Via Claude Desktop (After MCP Setup)
Ask Claude:
```
"Show me visitors from Leadfeeder"
"Which companies visited our site this week?"
"Show me high-confidence visitor identifications"
```

## Step 6: Enrich with Apollo (Find Contacts)

Once you identify a company, find decision-makers:

1. **Via Dashboard**: Click "Find Contacts" on any visitor company
2. **Via API**: POST to `/api/visitors/{company_key}/find-contacts`
3. **Via Claude Desktop**: "Find contacts at Acme Logistics"

This uses Apollo to search for:
- Decision makers at the company
- Job titles relevant to your offering (ops managers, warehouse directors, etc.)
- Verified email addresses

## Understanding Data Sources

Your platform merges data from 3 sources:

### 1. DIY Tracking (Your Tracking Script)
- ✅ **Pros**: Free, unlimited, you control everything
- ❌ **Cons**: Lower company identification rate (~20-40%)
- **Method**: MaxMind GeoLite2 IP-to-ASN matching

### 2. Leadfeeder (Free Tier)
- ✅ **Pros**: Better identification rate (~60-80%), includes company details
- ❌ **Cons**: 7-day expiration, 100 companies/month limit, requires scraping
- **Method**: Proprietary IP-to-company database

### 3. Apollo Enrichment (Paid)
- ✅ **Pros**: Find actual contacts at companies, verified emails
- ❌ **Cons**: Costs credits ($0.50/phone reveal)
- **Method**: B2B contact database

**Best Practice**: Use all 3 together for maximum coverage and confidence.

## Troubleshooting

### "Login failed" Error

**Cause**: Invalid credentials or Leadfeeder login page changed

**Fix**:
1. Verify credentials in `.env` are correct
2. Try logging in manually at https://app.leadfeeder.com
3. Check if Leadfeeder added CAPTCHA or 2FA
4. Run scraper in non-headless mode to debug:
   ```python
   scraper = LeadfeederScraper()
   scraper.init_driver(headless=False)  # You'll see the browser
   scraper.login()
   ```

### "No companies found" Error

**Possible Causes**:
- Leadfeeder UI changed (CSS selectors outdated)
- No recent visitors to your site
- Leadfeeder free trial expired

**Fix**:
1. Check if data shows in Leadfeeder dashboard manually
2. Update CSS selectors in `leadfeeder_scraper.py` if UI changed
3. Verify Leadfeeder tracking is installed on WordPress

### ChromeDriver Errors

**Error**: "chromedriver executable needs to be in PATH"

**Fix**:
```bash
pip install webdriver-manager
```

The system uses `webdriver-manager` to auto-download ChromeDriver.

### Scheduler Not Running

**Check scheduler status**:
```bash
curl http://localhost:7000/api/scheduler/status
```

**Verify in .env**:
```env
SCHEDULER_ENABLED=true
```

**Check logs**:
```bash
tail -f logs/backend.log | grep scheduler
```

## Production Deployment Notes

### Railway Deployment

✅ **Chrome/Chromium is now included in the deployment!**

The `nixpacks.toml` file now includes Chromium and ChromeDriver:

```toml
[phases.setup]
nixPkgs = ["python312", "nodejs_20", "chromium", "chromedriver"]
```

**Required Environment Variables on Railway:**

Set these in your Railway project settings:

```env
LEADFEEDER_EMAIL=your-leadfeeder-email@example.com
LEADFEEDER_PASSWORD=your-leadfeeder-password
SCHEDULER_ENABLED=true
```

**How to Set Environment Variables on Railway:**

1. Go to your Railway project dashboard
2. Click on your service
3. Go to "Variables" tab
4. Add the three variables above
5. Redeploy the service

**Manual Sync After Deployment:**

1. Go to your deployed app's Analytics tab
2. Look for the "Leadfeeder" integration card
3. Click the **"Sync Now"** button to manually trigger a scrape
4. The scraper will run and populate visitor data

**Automated Daily Syncs:**

Once configured, the scheduler will automatically:
- Scrape Leadfeeder data daily at 2 AM UTC
- Reconcile with your DIY tracking data every 2 hours
- Display combined results in the Visitors tab

### Alternative Options (if Railway has issues)

**Option A**: Use a separate server for scraping (e.g., DigitalOcean VPS with Chrome installed)

**Option B**: Use a cloud-based scraping service (Browserless.io, ScrapingBee, etc.)

### Recommended Strategy

For production, we recommend:
- **DIY tracking** (your script) → Always active on Railway
- **Leadfeeder scraping** → Now runs on Railway with Chromium
- **Scheduler** → Handles automatic daily syncs

This provides a fully automated visitor identification pipeline.

## Data Privacy & Compliance

### GDPR Considerations

Leadfeeder data contains:
- Company names and domains (business data, not personal)
- IP addresses (can be personal data)
- Visit behavior

**Recommendations**:
- Include visitor tracking in your privacy policy
- Provide opt-out mechanism if required
- Don't store personal emails from identified individuals
- Only store business contact information

### Data Retention

Configure retention in `config.py`:

```python
VISITOR_DATA_RETENTION_DAYS = 365  # Keep for 1 year
```

Old data is automatically cleaned up by the scheduler.

## Cost Analysis

### Leadfeeder Free Tier Limits
- 100 companies identified per month
- 7-day data retention
- Basic company information

### When to Upgrade Leadfeeder
If you exceed 100 companies/month consistently, consider:
- **Leadfeeder Premium**: $139/month (unlimited companies, full history)
- **Alternative**: Just use DIY tracking + Apollo (our free tier)

### Apollo Costs (for enrichment)
- Phone number reveal: $0.50/contact
- Company search: Free
- Email verification: Included

**Typical monthly cost**: $50-200 depending on volume

## Alternative to Leadfeeder

If you don't want to use Leadfeeder, you can rely solely on:
1. **Your DIY tracking** (MaxMind GeoLite2) - Free, ~30% identification rate
2. **Apollo company search** - Search by domain when you get a hit

**This is sufficient for most use cases** - Leadfeeder just increases identification accuracy.

## Next Steps

1. ✅ Sign up for Leadfeeder free account
2. ✅ Add credentials to `.env`
3. ✅ Install Leadfeeder tracking on WordPress
4. ✅ Test scraping locally
5. ✅ Deploy backend to Railway
6. ✅ Install your DIY tracking on WordPress
7. ✅ Monitor visitor identification in dashboard

---

**Questions?** Check the logs at `logs/backend.log` or test manually with Python.
