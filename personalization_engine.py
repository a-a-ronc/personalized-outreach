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
