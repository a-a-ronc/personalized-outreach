# Personalized Outreach System

Generate 1:1-feeling B2B outreach at scale with strict personalization controls. The system uses deterministic logic for pain themes, CTA selection, certainty level, and follow-up framing. The LLM only writes a single personalization sentence.

## What This Includes

- CLI campaign generator (CSV in, CSV out)
- Local upload UI (simple web app)
- Campaign Studio (React + API) with campaigns, audience, content, emails, statistics, and settings
- Deterministic personalization control object (pain theme, certainty, equipment anchors)
- ICP confidence scoring that drives verb strength and CTA assertiveness

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
OPENAI_API_KEY=your-openai-api-key-here
SENDGRID_API_KEY=your-sendgrid-api-key-here
```

### 3. Generate Your First Campaign (CLI)

```bash
python main.py --input data/Master_Leads_Populated_ICP_Equipment.csv --output output/campaigns.csv --limit 10
```

### 4. Local Web App (Optional)

```bash
python webapp/app.py
```

Then open `http://127.0.0.1:5000`. Upload a CSV, click Generate, and download the output from the page. Output files are saved to `output/`.

### 5. Campaign Studio (React + API)

Backend (API):

```bash
python backend/app.py
```

Frontend (React):

```bash
cd dashboard
npm install
npm run dev
```

Open the URL printed by Vite (default `http://127.0.0.1:5173`). If the backend port differs, set it in the sidebar API field or export:

```bash
set VITE_API_URL=http://127.0.0.1:7000
```

## Personalization Architecture

- Deterministic control object per lead:
  - `pain_theme`
  - `certainty_level`
  - `equipment_anchor`
  - `personalization_sentence` (LLM only)
- ICP confidence scoring: `high | medium | low`
  - Influences certainty language and CTA assertiveness
- Pain library: hard-coded by ICP segment and role level
- CTA selection: deterministic by pain theme
- Follow-up: reinforcement only, same pain theme, slightly higher certainty (unless low)
- Negative space: sanitizer strips marketing verbs, features, and benefit phrases

## CSV Input Format

Required columns:
- `Company`
- `Industry`
- `Email address`
- `Full name`

Optional columns:
- `Notes`
- `ICP Match`
- `Equipment`
- `Job title`

## Output CSV (Key Fields)

- `recipient_name`, `recipient_email`, `recipient_job_title`
- `company_name`, `first_name`, `industry`, `icp_match`, `icp_confidence`
- `email_sequence`, `subject`, `body`, `sender_name`, `sender_email`, `sender_title`
- `personalization_sentence`
- `personalization_object` (JSON)
- `pain_theme`, `certainty_level`, `pain_statement`
- `equipment`, `equipment_anchor`, `equipment_category`, `software_mention`
- `cta_label`, `cta_line`, `credibility_anchor`, `reinforcement_line`

## Campaign Studio Data

- Campaigns are stored in `data/campaigns.json`
- Uploaded lead lists go to `data/uploads/`
- Generated campaigns are stored in `output/`

### Settings in Campaign Studio

- Daily send limit
- Follow-up delay (days)
- Send window days and times
- Timezone label (MST - Mountain Standard Time)
- Sender account rotation and tracking toggles

### Statistics

- `scheduled` auto-populates from output CSV row count
- `sent`, `delivered`, `opened`, `replied`, `successful`, `bounced`, `unsubscribed` initialize to 0
- Stats are read-only in the UI and API for now

## Configuration

Edit `config.py` to adjust:

- `OPENAI_MODEL`
- `OPENAI_TEMPERATURE`
- `OPENAI_MAX_TOKENS`
- `MAX_EMAILS_PER_DAY`
- `BATCH_SIZE`
- `API_DELAY_SECONDS`
- Sender profiles and signatures

## Troubleshooting

### "Configuration errors: OPENAI_API_KEY not set"

Create a `.env` file in the project root based on `.env.example` and add your API keys.

### "Missing required columns"

Ensure your input CSV has `Company`, `Industry`, `Email address`, and `Full name`.

### Personalization quality is poor

Edit `templates/personalization_prompt.txt` and regenerate. The prompt expects a single sentence (18-25 words) and must only rephrase the approved pain statement.

## Project Structure

```
personalized-outreach/
  main.py
  config.py
  personalization_engine.py
  requirements.txt
  .env
  .env.example
  .gitignore
  README.md
  templates/
    personalization_prompt.txt
    email_1.txt
    email_2.txt
  data/
    Master_Leads_Populated_ICP_Equipment.csv
    campaigns.json
    uploads/
  output/
    campaigns_*.csv
  webapp/
    app.py
    templates/
    static/
  backend/
    app.py
  dashboard/
    package.json
    vite.config.js
    index.html
    src/
```

## License

Internal use only.
