# Apollo-Level Personalized Outreach Platform

Multi-channel outreach automation with AI personalization, voice calls, LinkedIn automation, and email sequences. Built for B2B sales teams targeting 3PL, logistics, and warehouse automation prospects.

## 🚀 Features

### Multi-Channel Sequences
- **Email**: SendGrid integration with 3 personalization modes
- **AI Voice Calls**: Bland.ai automated calling with dynamic scripts
- **LinkedIn**: Headless browser automation for connections and messages
- **Smart Delays**: Configurable wait times between touches

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

### Apollo Integration
- Lead enrichment API
- Phone number reveals (1 credit)
- Company data and signals
- Credit usage tracking

## ⚡ Quick Start (Replit - 5 Minutes)

### 1. Deploy to Replit
See [REPLIT_SETUP.md](REPLIT_SETUP.md) for detailed instructions.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Copy `.env.example` to `.env` and add your API keys:
```bash
OPENAI_API_KEY=sk-...
SENDGRID_API_KEY=SG...
BLAND_API_KEY=...
APOLLO_API_KEY=...
LINKEDIN_EMAIL=...
LINKEDIN_PASSWORD=...
```

### 4. Initialize Database
```bash
python migrate_db.py
```

### 5. Start Platform
```bash
./start.sh
```

Backend runs on port 7000.

### 6. Test Backend
```bash
python test_backend.py
```

All 8 tests should pass ✅

### 7. Open Dashboard
Navigate to `dashboard/index.html` in your browser.

## 📊 Platform Architecture

### Backend (Flask API)
- 13 REST endpoints for campaign management
- SQLite database with schema v2
- SendGrid email integration
- Bland.ai voice call orchestration
- LinkedIn headless browser automation
- Apollo enrichment with credit tracking

### Frontend (React Dashboard)
- Campaign builder with visual sequence editor
- Email preview with live personalization
- Variable autocomplete ({{first_name}}, {{company_name}}, etc.)
- Statistics and A/B testing dashboard
- Settings management

### Database Schema
**New Tables:**
- `sequences` - Multi-step outreach plans
- `sequence_steps` - Individual actions (email, call, LinkedIn)
- `signatures` - Outlook signature imports
- `outreach_log` - Sequence execution tracking

**Extended Tables:**
- `leads_people` - LinkedIn status, call history
- `leads_company` - Enrichment data from Apollo

## 🎯 Typical Campaign Flow

1. **Import Leads** from Apollo (14 leads recommended)
2. **Enrich Data** with phone numbers and company signals
3. **Create Campaign** with personalization mode
4. **Build Sequence**: Email → Wait 3d → Email → Wait 4d → Call → Wait 3d → LinkedIn
5. **Preview & Test** with real lead data
6. **Launch** automated sequence
7. **Monitor** statistics and reply tracking

## 💰 Cost Breakdown (Per Lead)

- OpenAI GPT-4: $0.10-0.15
- SendGrid: $0 (free tier 100/day)
- Bland.ai call: $0.80-1.20 (2-4 min avg)
- Apollo credit: $0.50 (phone reveal)
- LinkedIn: $0 (headless automation)

**Total: $1.40-2.00 per lead** (full 6-step omnichannel sequence)

## 📁 Project Structure

```
personalized-outreach/
├── backend/
│   └── app.py              # Flask API (2500+ lines)
├── dashboard/
│   └── src/
│       ├── App.jsx         # Main React app
│       └── components/
│           ├── SequenceBuilder.jsx
│           ├── EmailPreview.jsx
│           └── VariableAutocomplete.jsx
├── data/
│   ├── leads.db            # SQLite database
│   └── campaigns.json      # Campaign configs
├── templates/
│   ├── email_1.txt
│   └── personalization_prompt.txt
├── apollo_enrichment.py    # Apollo API integration
├── sequence_engine.py      # Orchestration engine
├── linkedin_automation.py  # Selenium automation
├── voice_calls.py          # Bland.ai integration
├── signature_manager.py    # Outlook signature import
├── personalization_engine.py
├── lead_registry.py        # Database layer
├── config.py
├── migrate_db.py
├── test_backend.py
├── requirements.txt
└── .replit                 # Replit deployment config
```

## 🔧 Configuration

Edit `config.py` or set environment variables:

```python
OPENAI_MODEL = "gpt-4"
OPENAI_TEMPERATURE = 0.7
MAX_EMAILS_PER_DAY = 50
LINKEDIN_MAX_CONNECTIONS_PER_DAY = 30
SENDGRID_API_KEY = "SG..."
BLAND_API_KEY = "..."
```

## 🐛 Troubleshooting

### Backend won't start
```bash
python migrate_db.py  # Initialize database
python test_backend.py  # Validate endpoints
```

### Email not sending
- Check SendGrid API key in `.env`
- Verify sender email is verified in SendGrid dashboard
- Review `logs/backend.log`

### LinkedIn automation blocked
- Use dedicated LinkedIn account (not personal)
- Reduce daily connection limit to 20
- Add random delays (2-5 min between actions)
- Use VPN if IP is flagged

### Apollo enrichment failing
- Verify API key in `.env`
- Check credit balance at apollo.io
- Review `logs/apollo.log`

## 📚 Documentation

- **[REPLIT_SETUP.md](REPLIT_SETUP.md)** - Deploy to Replit in 5 minutes
- **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** - Full technical documentation
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Pre-launch verification

## 🎓 Support

Run diagnostics: `python test_backend.py`
View logs: `tail -f logs/backend.log`
Check database: `sqlite3 data/leads.db`

## 📄 License

Internal use only. Not for redistribution.
