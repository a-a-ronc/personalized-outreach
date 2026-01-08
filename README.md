# Personalized Outreach System

Generate quality, 1:1-feeling B2B emails at scale using AI personalization with tight controls to prevent marketing-speak and hallucinations.

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
SENDER_EMAIL=your-email@example.com
SENDER_NAME=Your Name
```

### 3. Generate Your First Campaign

Start with a small test batch to validate quality:

```bash
python main.py --input data/leads.csv --output output/campaigns.csv --limit 10
```

This will:
- Load 10 leads from your CSV
- Generate personalization sentences using OpenAI
- Create 2 email variants per lead (Email 1 and Email 2)
- Save results to `output/campaigns.csv`

### 3b. Local Web App (Optional)

If you want a simple UI for the team, run the local web app:

```bash
python webapp/app.py
```

Then open `http://127.0.0.1:5000` in your browser. Upload a CSV, click Generate, and download the output from the page. Output files are saved to `output/`.

### 4. Review Output Quality

Open `output/campaigns.csv` and examine the `personalization_sentence` column.

**Look for:**

✅ **Green Flags (Good Quality)**
- Conversational, engineer-like tone
- Mentions industry pain points accurately
- Reads naturally when inserted into email
- Feels like domain expertise, not a sales pitch

❌ **Red Flags (Needs Improvement)**
- Marketing-speak or buzzwords
- Phrases like "I noticed", "I saw", "I came across"
- Too confident about specific company problems
- Awkward or unnatural phrasing
- Too generic ("Hope you're doing well" vibes)
- Too long (>30 words)

### 5. Iterate on Quality

If you see issues, edit `templates/personalization_prompt.txt` to:
- Add banned phrases
- Adjust approved sentence starters
- Include better examples
- Tighten constraints

Then regenerate and compare:

```bash
python main.py --input data/leads.csv --output output/campaigns_v2.csv --limit 10
```

**Expect 3-5 iterations** to hit 90%+ quality threshold.

## CSV Input Format

Your input CSV should have these columns:

- `Company Name` (required)
- `Domain` (required)
- `Industry` (required)
- `Notes` (optional - ICP notes, company type, etc.)

Additional columns are preserved but not used for personalization.

## Output Format

The output CSV contains:

- `company_name` - Company name
- `domain` - Company domain
- `first_name` - Recipient first name (currently defaults to "there")
- `email_sequence` - Email number (1 or 2)
- `subject` - Email subject line
- `body` - Full email body
- `personalization_sentence` - Generated sentence (for inspection)
- `industry` - Company industry
- `icp_notes` - ICP notes used for personalization

## Customizing Email Templates

Templates are in the `templates/` directory:

- `email_1.txt` - First outreach email
- `email_2.txt` - Follow-up email
- `personalization_prompt.txt` - OpenAI prompt for generating personalization

**Important:** Once you achieve good quality personalization:
1. Freeze `email_1.txt` and `email_2.txt` - don't keep tweaking
2. Only tune `personalization_prompt.txt` going forward
3. This creates consistency: "Same thoughtful engineer, different context"

### Template Placeholders

Available placeholders in email templates:
- `{{first_name}}` - Recipient first name
- `{{industry}}` - Company industry
- `{{personalization_sentence}}` - AI-generated personalization
- `{{company_name}}` - Company name

## Phase 1: Generation Pipeline (Current Phase)

**Goal:** Generate campaigns.csv with quality personalization for manual inspection

**Status:** ✅ Complete - You can now generate campaigns!

**Next Steps:**
1. Run generation on 25-50 leads
2. Manually inspect all personalization sentences
3. Iterate on prompt until 90%+ quality
4. Lock templates

## Phase 2: Quality Validation (Next)

Once personalization quality is consistently good (90%+ approval rate), move to Phase 2.

**Not implemented yet:**
- `python main.py --analyze` command for quality metrics
- Automated validation reports

For now, manual review in Excel/CSV viewer is recommended.

## Phase 3: Email Sending (Future)

After quality validation, you'll be able to send emails via SendGrid:

```bash
python main.py --send output/campaigns.csv --max-per-day 40
```

**Features (not yet implemented):**
- SendGrid integration
- Throttling (40 emails/day max)
- Randomized delays (30-120 seconds)
- Resume capability
- Send logging

## Configuration

Edit `config.py` to adjust:

- `OPENAI_MODEL` - Default: gpt-4o-mini (cost-efficient)
- `OPENAI_TEMPERATURE` - Default: 0.7 (controlled creativity)
- `OPENAI_MAX_TOKENS` - Default: 60 (~18-25 words)
- `MAX_EMAILS_PER_DAY` - Default: 40 (throttle limit)
- `BATCH_SIZE` - Default: 10 (leads per batch)
- `API_DELAY_SECONDS` - Default: 1.5 (delay between API calls)

## Non-Negotiable Constraints

These are built into the system to ensure quality:

1. **No marketing speak** - Prompt aggressively prevents this
2. **No hallucinations** - Only uses provided data fields
3. **Throttling enforced** - Code prevents >40 emails/day (Phase 3)
4. **Plain text only** - No HTML emails
5. **Manual review required** - No "generate and send" shortcut
6. **Freeze templates early** - Only tune personalization, not email body

## Troubleshooting

### "Configuration errors: OPENAI_API_KEY not set"

Create a `.env` file in the project root based on `.env.example` and add your API keys.

### "Missing required columns"

Ensure your input CSV has `Company Name`, `Industry`, and `Domain` columns.

### Personalization quality is poor

This is expected on first run. Edit `templates/personalization_prompt.txt`:
- Add specific examples of good/bad output
- Ban phrases you see appearing
- Adjust approved sentence starters

### API rate limiting errors

Increase `API_DELAY_SECONDS` in `config.py` to add more delay between requests.

## Cost Estimates

Using `gpt-4o-mini`:
- ~$0.001-0.002 per personalization sentence
- 100 leads ≈ $0.10-0.20
- 1,000 leads ≈ $1-2

Significantly cheaper than manual personalization at scale.

## Project Structure

```
personalized-outreach/
├── main.py                          # CLI entry point
├── config.py                        # Configuration
├── personalization_engine.py        # LLM integration
├── requirements.txt                 # Dependencies
├── .env                             # Your API keys (not in git)
├── .env.example                     # Template for .env
├── .gitignore                       # Git ignore rules
├── README.md                        # This file
├── templates/
│   ├── personalization_prompt.txt   # OpenAI prompt
│   ├── email_1.txt                  # First email
│   └── email_2.txt                  # Follow-up email
├── data/
│   └── [your CSV files]
└── output/
    └── [generated campaigns]
```

## Support

For issues or questions, review the implementation plan in `.claude/plans/` or modify the code directly.

## License

Internal use only.
