import os
import time
import logging
import re
from pathlib import Path
from openai import OpenAI
import pandas as pd
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_prompt_template():
    """Load the personalization prompt template"""
    template_path = Path(__file__).parent / "templates" / "personalization_prompt.txt"
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

MARKETING_PHRASES = [
    "improve",
    "increase",
    "boost",
    "maximize",
    "optimize",
    "streamline",
    "transform",
    "revolutionize",
    "unlock",
    "drive",
    "deliver",
    "enhance"
]

BENEFIT_PHRASES = [
    "so you can",
    "so that you can",
    "to help you",
    "which allows",
    "allowing you to",
    "so your team can"
]

CLARIFICATION_PHRASES = [
    "in other words",
    "to be clear",
    "that is to say",
    "meaning that"
]


def sanitize_personalization(sentence: str) -> str:
    cleaned = sentence.strip()

    for separator in [":", ";"]:
        if separator in cleaned:
            cleaned = cleaned.split(separator)[0].strip()

    if cleaned.count(",") >= 2:
        cleaned = cleaned.split(",")[0].strip()

    lower = cleaned.lower()
    for phrase in BENEFIT_PHRASES:
        idx = lower.find(phrase)
        if idx != -1:
            cleaned = cleaned[:idx].rstrip(" ,.-")
            lower = cleaned.lower()

    for phrase in CLARIFICATION_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)

    for phrase in MARKETING_PHRASES:
        cleaned = re.sub(r"\b" + re.escape(phrase) + r"\b", "", cleaned, flags=re.IGNORECASE)

    cleaned = " ".join(cleaned.split())
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."

    return cleaned


def validate_personalization(sentence: str) -> tuple[bool, list[str]]:
    """
    Validate that the personalization sentence meets quality requirements

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []

    # Check length (aim for 18-25 words)
    word_count = len(sentence.split())
    if word_count < 18:
        issues.append(f"Too short ({word_count} words)")
    elif word_count > 25:
        issues.append(f"Too long ({word_count} words)")

    # Check for banned phrases
    banned_phrases = [
        "i noticed",
        "i saw",
        "i came across",
        "your team",
        "your operation",
        "your company",
        "after researching"
    ]

    sentence_lower = sentence.lower()
    for phrase in banned_phrases:
        if phrase in sentence_lower:
            issues.append(f"Contains banned phrase: '{phrase}'")

    for phrase in MARKETING_PHRASES:
        if re.search(r"\b" + re.escape(phrase) + r"\b", sentence_lower):
            issues.append(f"Contains marketing verb: '{phrase}'")

    if ":" in sentence or ";" in sentence:
        issues.append("Contains feature list punctuation")

    if sentence.count(",") >= 2:
        issues.append("Contains list-like structure")

    is_valid = len(issues) == 0
    return is_valid, issues


def generate_personalization(company_data: dict, client: OpenAI, prompt_template: str) -> tuple[str, bool]:
    """
    Generate a personalization sentence for a company

    Returns:
        (generated_sentence, success_flag)
    """
    # Extract data from new dataset format
    company_name = company_data.get("Company", company_data.get("Company Name", ""))
    industry = company_data.get("Industry", "")
    icp_match = company_data.get("ICP Match", "")
    notes = company_data.get("Notes", "")
    equipment = company_data.get("Equipment", "")
    job_title = company_data.get("Job title", "")
    pain_theme = company_data.get("pain_theme", "")
    pain_statement = company_data.get("pain_statement", "")
    equipment_anchor = company_data.get("equipment_anchor", "")
    certainty_level = company_data.get("certainty_level", "")
    icp_confidence = company_data.get("icp_confidence", "")

    # Extract Apollo enrichment data (optional)
    technologies = company_data.get("technologies", "Not available")
    employee_count = company_data.get("employee_count", "Not available")
    job_postings_relevant = company_data.get("job_postings_relevant", "Not available")
    wms_system = company_data.get("wms_system", "unknown")
    equipment_signals = company_data.get("equipment_signals", "Not detected")

    # Convert to strings and handle NaN values
    company_name = str(company_name) if pd.notna(company_name) else ""
    industry = str(industry) if pd.notna(industry) else ""
    icp_match = str(icp_match) if pd.notna(icp_match) else ""
    notes = str(notes) if pd.notna(notes) else ""
    equipment = str(equipment) if pd.notna(equipment) else ""
    job_title = str(job_title) if pd.notna(job_title) else ""
    pain_theme = str(pain_theme) if pd.notna(pain_theme) else ""
    pain_statement = str(pain_statement) if pd.notna(pain_statement) else ""
    equipment_anchor = str(equipment_anchor) if pd.notna(equipment_anchor) else ""
    certainty_level = str(certainty_level) if pd.notna(certainty_level) else ""
    icp_confidence = str(icp_confidence) if pd.notna(icp_confidence) else ""

    # Convert enrichment data to strings
    technologies = str(technologies) if pd.notna(technologies) and technologies != "Not available" else "Not available"
    employee_count = str(employee_count) if pd.notna(employee_count) and employee_count != "Not available" else "Not available"
    job_postings_relevant = str(job_postings_relevant) if pd.notna(job_postings_relevant) and job_postings_relevant != "Not available" else "Not available"
    wms_system = str(wms_system) if pd.notna(wms_system) and wms_system != "unknown" else "unknown"
    equipment_signals = str(equipment_signals) if pd.notna(equipment_signals) and equipment_signals != "Not detected" else "Not detected"

    # Fill in the prompt template with new fields
    prompt = prompt_template.replace("{{company_name}}", company_name)
    prompt = prompt.replace("{{industry}}", industry)
    prompt = prompt.replace("{{icp_match}}", icp_match)
    prompt = prompt.replace("{{notes}}", notes)
    prompt = prompt.replace("{{equipment}}", equipment)
    prompt = prompt.replace("{{job_title}}", job_title)
    prompt = prompt.replace("{{pain_theme}}", pain_theme)
    prompt = prompt.replace("{{pain_statement}}", pain_statement)
    prompt = prompt.replace("{{equipment_anchor}}", equipment_anchor)
    prompt = prompt.replace("{{certainty_level}}", certainty_level)
    prompt = prompt.replace("{{icp_confidence}}", icp_confidence)

    # Fill in enrichment data
    prompt = prompt.replace("{{technologies}}", technologies)
    prompt = prompt.replace("{{employee_count}}", employee_count)
    prompt = prompt.replace("{{job_postings_relevant}}", job_postings_relevant)
    prompt = prompt.replace("{{wms_system}}", wms_system)
    prompt = prompt.replace("{{equipment_signals}}", equipment_signals)

    # Attempt generation with retries
    for attempt in range(Config.MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=Config.OPENAI_TEMPERATURE,
                max_tokens=Config.OPENAI_MAX_TOKENS
            )

            sentence = response.choices[0].message.content.strip()
            cleaned_sentence = sanitize_personalization(sentence)
            if cleaned_sentence:
                sentence = cleaned_sentence

            # Validate the generated sentence
            is_valid, issues = validate_personalization(sentence)

            if not is_valid:
                logger.warning(
                    f"Generated sentence for {company_name} failed validation: {', '.join(issues)}"
                )
                # We still return it, but log the issues for manual review

            return sentence, True

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed for {company_name}: {str(e)}")
            if attempt < Config.MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"All retries exhausted for {company_name}")
                return "", False

    return "", False


def batch_generate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate personalization sentences for a batch of leads

    Returns:
        DataFrame with new 'personalization_sentence' column
    """
    # Initialize OpenAI client
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    # Load prompt template
    prompt_template = load_prompt_template()

    # Prepare results
    results = []
    failed_count = 0

    logger.info(f"Generating personalization for {len(df)} leads...")

    for idx, row in df.iterrows():
        company_name = row.get("Company Name", f"Lead {idx}")
        logger.info(f"Processing {idx + 1}/{len(df)}: {company_name}")

        # Generate personalization
        sentence, success = generate_personalization(
            row.to_dict(),
            client,
            prompt_template
        )

        if not success:
            failed_count += 1
            logger.error(f"Failed to generate personalization for: {company_name}")

        results.append(sentence)

        # Rate limiting: delay between API calls
        if idx < len(df) - 1:  # Don't delay after the last one
            time.sleep(Config.API_DELAY_SECONDS)

    # Add results to dataframe
    df["personalization_sentence"] = results

    logger.info(f"✓ Generated {len(df) - failed_count}/{len(df)} personalization sentences")
    if failed_count > 0:
        logger.warning(f"⚠ {failed_count} failures - review output carefully")

    return df


# ====================
# NEW: Three Personalization Modes
# ====================

def extract_intent_signals(apollo_data: dict) -> dict:
    """Extract intent signals from Apollo enrichment data."""
    signals = {
        'primary_signal': None,
        'context': '',
        'signal_type': None
    }

    # Job postings signal
    job_postings = apollo_data.get('job_postings_relevant', 0)
    if job_postings and int(job_postings) > 0:
        signals['primary_signal'] = f"recently posted {job_postings} warehouse/automation roles"
        signals['signal_type'] = 'hiring'
        signals['context'] = f"expansion/hiring activity"
        return signals

    # Tech stack signal
    equipment_signals = apollo_data.get('equipment_signals', '')
    if equipment_signals and equipment_signals != 'Not detected':
        equipment_list = equipment_signals.split(',')
        if len(equipment_list) > 0:
            signals['primary_signal'] = f"currently using {equipment_list[0].strip()}"
            signals['signal_type'] = 'tech_stack'
            signals['context'] = f"existing automation infrastructure"
            return signals

    # WMS signal
    wms_system = apollo_data.get('wms_system', '')
    if wms_system and wms_system != 'unknown':
        signals['primary_signal'] = f"running {wms_system} WMS"
        signals['signal_type'] = 'wms'
        signals['context'] = f"established warehouse management system"
        return signals

    # Employee count growth signal
    employee_count = apollo_data.get('employee_count', 0)
    if employee_count:
        try:
            count = int(employee_count)
            if count > 300:
                signals['primary_signal'] = f"scaled to {count}+ employees"
                signals['signal_type'] = 'growth'
                signals['context'] = f"rapid growth phase"
                return signals
        except:
            pass

    # Default fallback
    industry = apollo_data.get('industry', '')
    company_name = apollo_data.get('Company', apollo_data.get('company_name', ''))
    if industry:
        signals['primary_signal'] = f"operates in {industry}"
        signals['signal_type'] = 'industry'
        signals['context'] = f"{industry} operations"

    return signals


def generate_signal_based_email(lead_data: dict, apollo_data: dict, client: OpenAI) -> tuple[str, bool]:
    """
    Generate signal-based personalization using intent data from Apollo.

    Returns:
        (opener_text, success_flag)
    """
    signals = extract_intent_signals(apollo_data)
    company_name = lead_data.get('Company', lead_data.get('company_name', ''))
    first_name = lead_data.get('first_name', lead_data.get('First Name', ''))

    if not signals['primary_signal']:
        return "", False

    prompt = f"""Write a 2-3 sentence email opener for a cold outreach email.

Context:
- Company: {company_name}
- Signal: {signals['primary_signal']}
- Signal type: {signals['signal_type']}

Requirements:
- Reference the specific signal naturally (not "I noticed")
- Connect the signal to a relevant pain point (capacity, labor costs, cube utilization)
- Keep it concise and direct
- No marketing fluff or buzzwords
- Total length: 40-60 words

Example format: "{company_name} {signals['primary_signal']}. [Connect to pain point]. [Transition to value prop]"

Write the opener:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=100
        )

        opener = response.choices[0].message.content.strip()
        return opener, True

    except Exception as e:
        logger.error(f"Signal-based generation failed: {e}")
        return "", False


def generate_fully_personalized_email(lead_data: dict, apollo_data: dict, client: OpenAI, template_context: dict) -> tuple[str, bool]:
    """
    Generate fully personalized email body using AI.

    Args:
        lead_data: Lead information (name, title, company)
        apollo_data: Enrichment data from Apollo
        client: OpenAI client
        template_context: Additional context (strategy, pain theme, etc.)

    Returns:
        (email_body, success_flag)
    """
    company_name = lead_data.get('Company', lead_data.get('company_name', ''))
    first_name = lead_data.get('first_name', lead_data.get('First Name', ''))
    title = lead_data.get('title', lead_data.get('Job title', ''))
    industry = apollo_data.get('industry', apollo_data.get('Industry', ''))
    employee_count = apollo_data.get('employee_count', '')
    pain_theme = template_context.get('pain_theme', 'throughput')
    strategy = template_context.get('strategy', 'conventional')

    # Build context
    context_parts = [f"Company: {company_name}"]
    if title:
        context_parts.append(f"Title: {title}")
    if industry:
        context_parts.append(f"Industry: {industry}")
    if employee_count:
        context_parts.append(f"Size: {employee_count} employees")

    context = "\n".join(context_parts)

    prompt = f"""Write a complete personalized cold email body (100-120 words) for Intralog, a warehouse storage systems company.

Recipient Context:
{context}

Pain Theme: {pain_theme}
Strategy: {strategy}

Intralog offers:
- Conventional: Racking systems, mezzanines, pick modules
- Semi-automation: High-density racking, pallet shuttles, VLMs
- Full automation: ASRS, conveyors, sortation systems

Email Structure:
1. Personalized opener (2 sentences) - reference their specific operational context
2. Value proposition (1-2 sentences) - how Intralog solves their challenge
3. Proof point (1 sentence) - specific case study or metric
4. Soft CTA (1 sentence) - "Worth a 15-minute call to evaluate cost per unit reduction?"

Requirements:
- Direct, operationally intelligent tone
- No buzzwords ("game-changer", "revolutionary")
- No "I noticed", "I saw", "reaching out"
- Focus on measurable ROI (cost per unit, throughput, cube utilization)

Write the email body:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert B2B copywriter for industrial sales. Write concise, direct emails that demonstrate operational knowledge."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=250
        )

        email_body = response.choices[0].message.content.strip()
        return email_body, True

    except Exception as e:
        logger.error(f"Fully personalized generation failed: {e}")
        return "", False


def generate_personalized_opener_email(lead_data: dict, apollo_data: dict, client: OpenAI) -> tuple[str, bool]:
    """
    Generate personalized opener (first 1-2 sentences only).
    Rest of email uses template.

    Returns:
        (opener_text, success_flag)
    """
    company_name = lead_data.get('Company', lead_data.get('company_name', ''))
    first_name = lead_data.get('first_name', lead_data.get('First Name', ''))
    title = lead_data.get('title', lead_data.get('Job title', ''))
    industry = apollo_data.get('industry', apollo_data.get('Industry', ''))

    # Build minimal context
    context_parts = [f"Company: {company_name}"]
    if title:
        context_parts.append(f"Role: {title}")
    if industry:
        context_parts.append(f"Industry: {industry}")

    context = "\n".join(context_parts)

    prompt = f"""Write a personalized 1-2 sentence opener for a cold email.

Context:
{context}

Requirements:
- Reference something specific about their company, role, or industry
- Natural and conversational
- No "I noticed", "I saw", "I came across"
- No marketing verbs (improve, boost, optimize)
- Total length: 20-30 words

Example: "{first_name}, {company_name}'s 3PL operations in Utah likely face the same cube utilization challenges most fulfillment centers are wrestling with right now."

Write the opener:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=80
        )

        opener = response.choices[0].message.content.strip()
        return opener, True

    except Exception as e:
        logger.error(f"Personalized opener generation failed: {e}")
        return "", False


def generate_email_by_mode(mode: str, lead_data: dict, apollo_data: dict, template_context: dict = None) -> tuple[str, bool]:
    """
    Generate email content based on personalization mode.

    Args:
        mode: 'signal_based', 'fully_personalized', or 'personalized_opener'
        lead_data: Lead information
        apollo_data: Apollo enrichment data
        template_context: Additional context for generation

    Returns:
        (generated_content, success_flag)
    """
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    if mode == 'signal_based':
        return generate_signal_based_email(lead_data, apollo_data, client)
    elif mode == 'fully_personalized':
        return generate_fully_personalized_email(lead_data, apollo_data, client, template_context or {})
    elif mode == 'personalized_opener':
        return generate_personalized_opener_email(lead_data, apollo_data, client)
    else:
        logger.error(f"Unknown personalization mode: {mode}")
        return "", False
