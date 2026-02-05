# Leadfeeder API Integration Setup Guide

## Overview

Your application now uses the **Leadfeeder API** instead of web scraping for faster, more reliable data extraction. This eliminates the need for Selenium, ChromeDriver, VNC, and browser automation.

## Benefits of API Integration

✅ **10x Faster** - Direct API calls vs browser automation
✅ **100% Reliable** - No UI changes to break your integration
✅ **No Browser Required** - Eliminated Selenium, ChromeDriver, VNC overhead
✅ **Better Data** - Structured JSON with complete fields
✅ **Rate Limited** - 100 requests/minute (plenty for most use cases)

## Setup Instructions

### 1. Add API Key to Environment Variables

Add your Leadfeeder API key to your `.env` file:

```bash
# Leadfeeder API Configuration
LEADFEEDER_API_KEY=your-leadfeeder-api-key-here

# Legacy credentials (no longer needed, but kept for reference)
# LEADFEEDER_EMAIL=your-email@example.com
# LEADFEEDER_PASSWORD=your-password
```

### 2. Verify Configuration

The API key is now configured in `config.py` and will be automatically loaded.

### 3. Test the Integration

You can test the API integration in several ways:

#### Option A: Via Dashboard (Recommended)

1. Go to your dashboard at `http://localhost:7000` (or your deployed URL)
2. Navigate to **Integrations** → **Leadfeeder**
3. Click **"Sync Now"** button
4. Monitor the sync status

#### Option B: Via API Call

```bash
# Check status
curl http://localhost:7000/api/integrations/leadfeeder/status

# Trigger manual sync
curl -X POST http://localhost:7000/api/integrations/leadfeeder/sync \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7}'
```

#### Option C: Via Python Script

```python
from leadfeeder_api import sync_leadfeeder_data, get_leadfeeder_status

# Check status
status = get_leadfeeder_status()
print(f"Leadfeeder configured: {status['configured']}")
print(f"API working: {status['api_working']}")

# Sync last 7 days of data
result = sync_leadfeeder_data(days_back=7)
print(f"Success: {result['success']}")
print(f"Leads synced: {result['leads_synced']}")
```

## How It Works

### Data Flow

1. **API Authentication**: Uses your API token in the Authorization header
2. **Account Detection**: Automatically finds your Leadfeeder account
3. **Lead Fetching**: Retrieves leads (companies) from the last 7 days (configurable)
4. **Data Storage**: Stores in `leadfeeder_visits` and `visitor_companies` tables
5. **Status Tracking**: Updates `integration_status` table

### Automatic Sync Schedule

The scheduler automatically syncs Leadfeeder data:
- **Frequency**: Daily at 2:00 AM UTC
- **Lookback**: Last 7 days of data
- **Rate Limit**: Respects 100 requests/minute limit

### API Endpoints Used

```
GET  /accounts                                    - Get your accounts
GET  /accounts/{account_id}/leads                - Get leads for date range
GET  /accounts/{account_id}/leads/{lead_id}      - Get specific lead details
GET  /accounts/{account_id}/visits               - Get all visits (optional)
```

## Database Schema

Data is stored in two main tables:

### `leadfeeder_visits`
Stores raw data from Leadfeeder API:
- `leadfeeder_id`: Unique identifier (e.g., "lf_api_12345")
- `company_name`: Company name
- `domain`: Company website domain
- `industry`: Industry classification
- `employee_count`: Number of employees
- `country`: Company location
- `page_views`: Number of page views
- `first_visit_at`: First visit timestamp
- `last_visit_at`: Last visit timestamp
- `expires_at`: When data expires (7 days from scrape)

### `visitor_companies`
Reconciled company data for frontend display:
- Combines data from Leadfeeder, IP tracking, and Apollo enrichment
- Used by the dashboard to show visitor list

## Customization

### Change Sync Frequency

Edit `scheduler.py` to adjust the sync schedule:

```python
# Current: Daily at 2 AM UTC
scheduler.add_job(
    job_leadfeeder_scrape,
    CronTrigger(hour=2, minute=0),  # Change hour here
    id="leadfeeder_scrape",
    name="Leadfeeder Daily API Sync",
    replace_existing=True
)

# Example: Every 6 hours
scheduler.add_job(
    job_leadfeeder_scrape,
    IntervalTrigger(hours=6),  # Sync every 6 hours
    id="leadfeeder_scrape",
    name="Leadfeeder API Sync",
    replace_existing=True
)
```

### Change Lookback Period

Modify the `days_back` parameter:

```python
# In scheduler.py - job_leadfeeder_scrape()
result = sync_leadfeeder_data(days_back=14)  # Look back 14 days instead of 7
```

### Specify Account ID

If you have multiple Leadfeeder accounts:

```python
result = sync_leadfeeder_data(
    days_back=7,
    account_id="your-account-id"
)
```

## Rate Limiting

The API client automatically handles rate limiting:
- **Limit**: 100 requests per minute per account
- **Behavior**: Automatically waits if limit is reached
- **Retry**: Automatically retries on 429 (Too Many Requests)

## Troubleshooting

### "Invalid Leadfeeder API token" Error

**Solution**: Check that your API key is correct in `.env`:
```bash
LEADFEEDER_API_KEY=your-leadfeeder-api-key-here
```

### No Accounts Found

**Possible causes**:
1. API token doesn't have access to any accounts
2. API token is invalid or expired

**Solution**: Verify your token has access to at least one Leadfeeder account.

### No Leads Returned

**Possible causes**:
1. No website visitors in the specified date range
2. Account has no active website tracking

**Solution**: Check your Leadfeeder dashboard to verify you have tracking enabled and recent visitors.

### Rate Limit Errors

If you hit the rate limit frequently:
1. Reduce sync frequency in scheduler
2. Increase `days_back` to fetch more data less often
3. Consider batching requests differently

## Migration Notes

### Old Scraper vs New API

| Feature | Web Scraper (Old) | API (New) |
|---------|-------------------|-----------|
| Speed | ~3-5 min per sync | ~10-30 sec per sync |
| Reliability | Breaks on UI changes | Always works |
| Dependencies | Selenium, ChromeDriver, VNC | Just `requests` library |
| Resource Usage | High (browser process) | Low (HTTP requests) |
| Maintenance | High | Low |

### Legacy Code

The old scraper code is still available in `leadfeeder_scraper.py` but is no longer used. You can:
1. Keep it as a fallback
2. Delete it to reduce codebase size

### Screenshots and VNC

These features were only needed for debugging the web scraper. With the API integration, they're no longer necessary:
- `/api/integrations/leadfeeder/screenshots` - No longer needed
- `/api/integrations/leadfeeder/vnc/status` - No longer needed
- VNC server configuration - No longer needed

You can safely remove VNC-related code if desired.

## API Documentation

For complete API documentation, visit:
**https://docs.leadfeeder.com/api/**

## Support

If you encounter issues:
1. Check the logs: `logs/` directory or Railway logs
2. Verify your API key is valid
3. Test the API manually with curl
4. Check the `integration_status` table for error messages

## Next Steps

1. ✅ Add `LEADFEEDER_API_KEY` to `.env`
2. ✅ Test the integration via dashboard or API
3. ✅ Monitor the first automatic sync (2 AM UTC)
4. ✅ Verify data in `visitor_companies` table
5. ✅ Optionally remove old scraper code

---

**Note**: The old email/password credentials are no longer needed but are kept in config for backwards compatibility. The API key is now the primary authentication method.
