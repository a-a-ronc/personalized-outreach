# Apollo-Level Personalized Outreach Platform

Multi-channel outreach automation with AI personalization, voice calls, LinkedIn automation, email sequences, and website visitor identification. Built for B2B sales teams targeting 3PL, logistics, and warehouse automation prospects.

## Features

### Multi-Channel Sequences
- **Email**: SendGrid integration with 3 personalization modes
- **AI Voice Calls**: Bland.ai automated calling with dynamic scripts
- **LinkedIn**: Headless browser automation for connections and messages
- **Smart Delays**: Configurable wait times between touches

### Website Visitor Identification (NEW)
- **DIY IP Tracking**: MaxMind GeoLite2 IP-to-company resolution
- **Leadfeeder Integration**: Scrapes visitor data before 7-day expiry
- **Data Reconciliation**: Merges data sources with confidence scoring
- **Background Jobs**: APScheduler for automated data collection
- **Find Contacts**: Apollo enrichment for identified companies

### Claude Desktop Integration (NEW)
- **MCP Server**: Ask Claude questions about your campaigns directly
- **Real-time Analytics**: Query visitor stats, campaign performance, and email health
- **Natural Language**: "Show me visitors from last week" or "Which campaigns have low open rates?"
- **Read-only Access**: Secure analytics without destructive operations

### 3 Personalization Modes
1. **Signal-Based**: Intent data from Apollo (job postings, tech stack, funding)
2. **Fully Personalized**: AI writes complete email (100-120 words)
3. **Personalized Opener**: AI writes first 1-2 sentences only

### Rich Campaign Studio
- Variable autocomplete (24 template variables)
- Live email preview with test sending
- Visual sequence builder (drag-and-drop)
- Campaign statistics and A/B testing
- Outlook signature import with logo embedding
- **Dark Mode**: System-aware theming with manual toggle

### Apollo Integration
- Lead enrichment API
- Phone number reveals (1 credit)
- Company data and signals
- Credit usage tracking

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and add your API keys:
```bash
# Required
OPENAI_API_KEY=sk-...
SENDGRID_API_KEY=SG...
SENDER_EMAIL=you@domain.com
SENDER_NAME=Your Name

# Optional - Website Visitor Identification
MAXMIND_LICENSE_KEY=your_maxmind_key
LEADFEEDER_EMAIL=your_email
LEADFEEDER_PASSWORD=your_password

# Optional - Other Integrations
BLAND_API_KEY=...
APOLLO_API_KEY=...
LINKEDIN_EMAIL=...
LINKEDIN_PASSWORD=...
```

### 3. Initialize Database
```bash
python migrate_db.py
```

### 4. Start Backend
```bash
python backend/app.py
```
Backend runs on port 7000.

### 5. Start Dashboard
```bash
cd dashboard
npm install
npm run dev
```
Dashboard runs on port 5173.

### 6. Test Backend
```bash
python test_backend.py
```
All tests should pass.

## Website Visitor Tracking Setup

### MaxMind GeoLite2 (Free IP Lookup)
1. Sign up at https://www.maxmind.com/en/geolite2/signup
2. Create a license key
3. Add to `.env`: `MAXMIND_LICENSE_KEY=your_key`
4. Databases auto-download on first run

### Leadfeeder Integration (Optional)
1. Create free account at https://www.leadfeeder.com
2. Add credentials to `.env`
3. Data scraped daily before 7-day expiry

### Add Tracking Code to Your Website
From the Analytics tab, copy the tracking snippet:
```html
<script>
(function(w,d,s,u,k){
  w._vt=w._vt||[];
  var js,fjs=d.getElementsByTagName(s)[0];
  if(d.getElementById(k))return;
  js=d.createElement(s);js.id=k;
  js.src=u+'/api/track/script.js';
  fjs.parentNode.insertBefore(js,fjs);
})(window,document,'script','YOUR_BACKEND_URL','vt-script');
</script>
```

## Platform Architecture

### Backend (Flask API)
- REST endpoints for campaign management
- SQLite database with schema v6
- SendGrid email integration
- Bland.ai voice call orchestration
- LinkedIn headless browser automation
- Apollo enrichment with credit tracking
- Website visitor tracking and identification
- APScheduler background jobs

### Frontend (React Dashboard)
- Campaign builder with visual sequence editor
- Email preview with live personalization
- Variable autocomplete
- Statistics and A/B testing dashboard
- Website visitor table and analytics
- Dark mode support (system-aware + manual toggle)
- Settings management

### Database Schema
**Visitor Tracking Tables (v6):**
- `visitor_raw` - All raw visit data
- `visitor_ip_resolution` - MaxMind lookup results
- `leadfeeder_visits` - Scraped Leadfeeder data
- `visitor_companies` - Reconciled companies
- `visitor_sessions` - Visit sessions
- `scheduled_jobs` - Background job tracking

**Campaign Tables:**
- `sequences` - Multi-step outreach plans
- `sequence_steps` - Individual actions
- `signatures` - Outlook signature imports
- `outreach_log` - Sequence execution tracking

## Typical Campaign Flow

1. **Import Leads** from Apollo or identified website visitors
2. **Enrich Data** with phone numbers and company signals
3. **Create Campaign** with personalization mode
4. **Build Sequence**: Email -> Wait 3d -> Email -> Wait 4d -> Call -> Wait 3d -> LinkedIn
5. **Preview & Test** with real lead data
6. **Launch** automated sequence
7. **Monitor** statistics and reply tracking

## Security Best Practices

This platform handles sensitive data. Follow these guidelines:

### Environment Variables
- **NEVER** commit `.env` to version control
- Use `.env.example` for documentation
- Rotate API keys periodically

### Files to Exclude (in .gitignore)
```
.env
*.db
data/GeoLite2-*.mmdb
logs/
__pycache__/
node_modules/
```

### Data Protection
- API keys stored in environment variables only
- Database contains PII - handle with care
- Rate limiting on API endpoints
- CORS restricted to specific domains

### Access Control
- This is an internal tool - no public access
- Validate all user inputs
- Sanitize data before database operations

## Cost Breakdown (Per Lead)

- OpenAI GPT-4: $0.10-0.15
- SendGrid: $0 (free tier 100/day)
- Bland.ai call: $0.80-1.20 (2-4 min avg)
- Apollo credit: $0.50 (phone reveal)
- LinkedIn: $0 (headless automation)
- MaxMind: $0 (free GeoLite2)
- Leadfeeder: $0 (free tier)

**Total: $1.40-2.00 per lead** (full omnichannel sequence)

## Project Structure

```
personalized-outreach/
├── backend/
│   └── app.py              # Flask API
├── dashboard/
│   └── src/
│       ├── App.jsx         # Main React app
│       └── components/
│           ├── SequenceBuilder.jsx
│           ├── EmailPreview.jsx
│           ├── VisitorTable.jsx      # NEW
│           ├── VisitorAnalytics.jsx  # NEW
│           └── ...
├── data/
│   ├── leads.db            # SQLite database
│   ├── GeoLite2-City.mmdb  # MaxMind DB (auto-downloaded)
│   └── GeoLite2-ASN.mmdb   # MaxMind DB (auto-downloaded)
├── visitor_tracking.py     # NEW - Visit recording
├── ip_resolver.py          # NEW - MaxMind integration
├── leadfeeder_scraper.py   # NEW - Leadfeeder automation
├── visitor_reconciliation.py # NEW - Data merging
├── scheduler.py            # NEW - Background jobs
├── apollo_enrichment.py
├── sequence_engine.py
├── linkedin_automation.py
├── personalization_engine.py
├── lead_registry.py
├── config.py
├── migrate_db.py
└── requirements.txt
```

## Configuration

Edit `config.py` or set environment variables:

```python
# Core
OPENAI_MODEL = "gpt-4o"
OPENAI_TEMPERATURE = 0.7
MAX_EMAILS_PER_DAY = 50

# Visitor Tracking
VISITOR_RATE_LIMIT_PER_HOUR = 100
VISITOR_SESSION_TIMEOUT_MINUTES = 30
VISITOR_ALLOWED_DOMAINS = ["your-domain.com"]
VISITOR_DATA_RETENTION_DAYS = 365
SCHEDULER_ENABLED = True
```

## Troubleshooting

### Backend won't start
```bash
python migrate_db.py  # Initialize database
python test_backend.py  # Validate endpoints
```

### Email not sending
- Check SendGrid API key in `.env`
- Verify sender email is verified in SendGrid dashboard
- Review `logs/backend.log`

### Visitor tracking not working
- Verify MaxMind license key is valid
- Check that databases downloaded to `data/` directory
- Ensure tracking code is on your website
- Check CORS allows your domain

### LinkedIn automation blocked
- Use dedicated LinkedIn account (not personal)
- Reduce daily connection limit to 20
- Add random delays (2-5 min between actions)

## Deployment

### Production Deployment (Railway - Recommended)

Deploy to Railway for 24/7 uptime and visitor tracking:

1. **See [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)** for complete guide
2. Push code to GitHub
3. Deploy from Railway dashboard
4. Configure environment variables
5. Get your public URL for WordPress tracking

**Why Railway?**
- $5/month free credit (sufficient for most use cases)
- Automatic HTTPS and SSL
- Zero cold starts (always active)
- Perfect for visitor tracking that needs 24/7 uptime

### Other Deployment Options

- **[REPLIT_SETUP.md](REPLIT_SETUP.md)** - Deploy to Replit (development/testing)

## Documentation

- **[RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)** - Production deployment guide
- **[MCP_SETUP.md](MCP_SETUP.md)** - Claude Desktop integration setup
- **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** - Technical documentation
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Pre-launch verification

## Support

Run diagnostics: `python test_backend.py`
View logs: `tail -f logs/backend.log`
Check database: `sqlite3 data/leads.db`

## License

Internal use only. Not for redistribution.
