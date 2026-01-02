import os
import time
import logging
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


def validate_personalization(sentence: str) -> tuple[bool, list[str]]:
    """
    Validate that the personalization sentence meets quality requirements

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []

    # Check length (aim for 10-30 words)
    word_count = len(sentence.split())
    if word_count < 10:
        issues.append(f"Too short ({word_count} words)")
    elif word_count > 30:
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

    is_valid = len(issues) == 0
    return is_valid, issues


def generate_personalization(company_data: dict, client: OpenAI, prompt_template: str) -> tuple[str, bool]:
    """
    Generate a personalization sentence for a company

    Returns:
        (generated_sentence, success_flag)
    """
    # Extract data
    company_name = company_data.get("Company Name", "")
    industry = company_data.get("Industry", "")
    icp_notes = company_data.get("Notes", "")

    # Fill in the prompt template
    prompt = prompt_template.replace("{{company_name}}", company_name)
    prompt = prompt.replace("{{industry}}", industry)
    prompt = prompt.replace("{{icp_notes}}", icp_notes)

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
