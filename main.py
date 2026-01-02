import argparse
import sys
from pathlib import Path
import pandas as pd
import logging
from config import Config
from personalization_engine import batch_generate

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_first_name(company_name: str) -> str:
    """
    Extract first name from company name or return generic greeting

    For now, returns generic "there" - can be enhanced later with contact data
    """
    return "there"


def load_email_template(template_name: str) -> tuple[str, str]:
    """
    Load email template and extract subject and body

    Returns:
        (subject, body_template)
    """
    template_path = Path(__file__).parent / "templates" / template_name
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split on first newline after "Subject:"
    lines = content.split("\n")
    subject = ""
    body_lines = []

    for i, line in enumerate(lines):
        if line.startswith("Subject:"):
            subject = line.replace("Subject:", "").strip()
            # Body starts after the subject line and a blank line
            body_lines = lines[i + 2:]  # Skip subject and blank line
            break

    body = "\n".join(body_lines)
    return subject, body


def fill_template(template: str, data: dict) -> str:
    """Fill template placeholders with data"""
    result = template
    for key, value in data.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def generate_campaigns(input_path: str, output_path: str, limit: int = None):
    """
    Main function to generate personalized email campaigns

    Args:
        input_path: Path to input CSV with leads
        output_path: Path to output CSV with campaigns
        limit: Optional limit on number of leads to process
    """
    logger.info("=" * 60)
    logger.info("Personalized Outreach Campaign Generator")
    logger.info("=" * 60)

    # Validate configuration
    try:
        Config.validate()
        logger.info("✓ Configuration validated")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("\nPlease create a .env file based on .env.example")
        sys.exit(1)

    # Load input CSV
    logger.info(f"\nLoading leads from: {input_path}")
    try:
        df = pd.read_csv(input_path)
        logger.info(f"✓ Loaded {len(df)} leads")
    except Exception as e:
        logger.error(f"Failed to load CSV: {e}")
        sys.exit(1)

    # Apply limit if specified
    if limit:
        df = df.head(limit)
        logger.info(f"✓ Limited to {limit} leads for testing")

    # Validate required columns
    required_columns = ["Company Name", "Industry", "Domain"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        logger.error(f"Missing required columns: {', '.join(missing)}")
        logger.error(f"Available columns: {', '.join(df.columns)}")
        sys.exit(1)

    # Ensure Notes column exists
    if "Notes" not in df.columns:
        df["Notes"] = ""
        logger.info("⚠ No 'Notes' column found - using empty strings for ICP notes")

    logger.info("✓ Required columns present")

    # Generate personalization sentences
    logger.info("\n" + "=" * 60)
    logger.info("Generating personalization sentences...")
    logger.info("=" * 60)

    df = batch_generate(df)

    # Load email templates
    logger.info("\nLoading email templates...")
    email_1_subject, email_1_body = load_email_template("email_1.txt")
    email_2_subject, email_2_body = load_email_template("email_2.txt")
    logger.info("✓ Templates loaded")

    # Generate campaign rows
    logger.info("\nGenerating campaign output...")
    logger.info(f"Rotating between {len(Config.SENDER_PROFILES)} senders:")
    for profile in Config.SENDER_PROFILES:
        logger.info(f"  - {profile['full_name']} ({profile['title']})")

    campaign_rows = []

    for idx, row in df.iterrows():
        company_name = row["Company Name"]
        domain = row["Domain"]
        industry = row.get("Industry", "")
        icp_notes = row.get("Notes", "")
        personalization = row["personalization_sentence"]
        first_name = extract_first_name(company_name)

        # Assign sender in round-robin fashion
        sender = Config.get_sender_profile(idx)

        # Data for template filling
        template_data = {
            "first_name": first_name,
            "industry": industry,
            "personalization_sentence": personalization,
            "company_name": company_name,
            "signature": sender["signature"]
        }

        # Email 1
        campaign_rows.append({
            "company_name": company_name,
            "domain": domain,
            "first_name": first_name,
            "email_sequence": 1,
            "subject": fill_template(email_1_subject, template_data),
            "body": fill_template(email_1_body, template_data),
            "personalization_sentence": personalization,
            "industry": industry,
            "icp_notes": icp_notes,
            "sender_name": sender["full_name"],
            "sender_email": sender["email"],
            "sender_title": sender["title"]
        })

        # Email 2 (reuses same personalization and sender)
        campaign_rows.append({
            "company_name": company_name,
            "domain": domain,
            "first_name": first_name,
            "email_sequence": 2,
            "subject": fill_template(email_2_subject, template_data),
            "body": fill_template(email_2_body, template_data),
            "personalization_sentence": personalization,
            "industry": industry,
            "icp_notes": icp_notes,
            "sender_name": sender["full_name"],
            "sender_email": sender["email"],
            "sender_title": sender["title"]
        })

    # Create output dataframe
    output_df = pd.DataFrame(campaign_rows)

    # Save to CSV
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    output_df.to_csv(output_path, index=False)
    logger.info(f"✓ Saved campaign to: {output_path}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total leads processed: {len(df)}")
    logger.info(f"Campaign rows generated: {len(output_df)} ({len(df)} × 2 emails)")
    logger.info(f"Output file: {output_path}")

    # Show sender distribution
    logger.info("\nSender distribution:")
    sender_counts = output_df[output_df["email_sequence"] == 1]["sender_name"].value_counts()
    for sender, count in sender_counts.items():
        logger.info(f"  - {sender}: {count} leads")

    # Count failures (empty personalization sentences)
    failed = len(df[df["personalization_sentence"] == ""])
    if failed > 0:
        logger.warning(f"\n⚠ {failed} personalization failures - review manually")

    logger.info("\n" + "=" * 60)
    logger.info("NEXT STEPS")
    logger.info("=" * 60)
    logger.info("1. Open the output CSV and review the 'personalization_sentence' column")
    logger.info("2. Look for red flags:")
    logger.info("   - Marketing speak")
    logger.info("   - Phrases like 'I noticed' or 'I saw'")
    logger.info("   - Too generic or too specific")
    logger.info("   - Awkward phrasing")
    logger.info("3. If quality is <90%, iterate on templates/personalization_prompt.txt")
    logger.info("4. Once quality is good, you're ready for Phase 2")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate personalized outreach campaigns"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV file with leads"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to output CSV file for campaigns"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of leads to process (for testing)"
    )

    args = parser.parse_args()

    # Run generation
    generate_campaigns(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
