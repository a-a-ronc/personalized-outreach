import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration management for personalized outreach system"""

    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = "gpt-4"  # Cost-efficient model
    OPENAI_TEMPERATURE = 0.7  # Controlled creativity
    OPENAI_MAX_TOKENS = 60  # ~18-25 words for personalization

    # SendGrid Configuration
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

    # Apollo.io Configuration
    APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
    APOLLO_RATE_LIMIT_DELAY = 0.5  # seconds between calls
    APOLLO_PERSON_TTL_DAYS = 90
    APOLLO_COMPANY_TTL_DAYS = 180
    APOLLO_SUPPRESSION_DAYS = 180
    APOLLO_BULK_MATCH_SIZE = 10

    # Bland.ai Voice Call Configuration
    BLAND_API_KEY = os.getenv("BLAND_API_KEY")

    # LinkedIn Automation Configuration
    LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
    LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
    LINKEDIN_MAX_CONNECTIONS_PER_DAY = 30
    LINKEDIN_MIN_DELAY_SECONDS = 120  # 2 minutes between actions
    LINKEDIN_MAX_DELAY_SECONDS = 300  # 5 minutes

    # Base URL for webhooks
    BASE_URL = os.getenv("BASE_URL", "http://localhost:7000")

    # Sender Profiles with Email Signatures
    SENDER_PROFILES = [
        {
            "name": "Aaron",
            "full_name": "Aaron Cendejas",
            "email": "aaron@intralog.io",
            "title": "Senior Systems Engineer",
            "company": "Intralog",
            "phone": "(714) 697-6431",
            "signature": """Aaron Cendejas
Senior Systems Engineer, Intralog
aaron@intralog.io | (714) 697-6431
www.intralog.io"""
        },
        {
            "name": "Michael",
            "full_name": "Michael Schulte",
            "email": "michael@intralog.io",
            "title": "VP of Engineering",
            "company": "Intralog",
            "phone": "(765) 432-6236",
            "signature": """Michael Schulte
VP of Engineering, Intralog
michael@intralog.io | (765) 432-6236
www.intralog.io"""
        },
        {
            "name": "Mark",
            "full_name": "Mark Westover",
            "email": "mark@intralog.io",
            "title": "CEO",
            "company": "Intralog",
            "phone": "(385) 500-3950",
            "signature": """Mark Westover
CEO, Intralog
mark@intralog.io | (385) 500-3950
www.intralog.io"""
        }
    ]

    # Rate Limiting
    BATCH_SIZE = 10  # Process leads in batches
    API_DELAY_SECONDS = 1.5  # Delay between API calls
    MAX_RETRIES = 3  # Retry failed API calls

    # Email Sending
    MAX_EMAILS_PER_DAY = 40  # Throttle limit
    MIN_SEND_DELAY = 30  # Minimum seconds between sends
    MAX_SEND_DELAY = 120  # Maximum seconds between sends

    @classmethod
    def validate(cls):
        """Validate that required configuration is present"""
        errors = []

        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY not set in .env file")

        if not cls.SENDGRID_API_KEY:
            errors.append("SENDGRID_API_KEY not set in .env file")

        if not cls.SENDER_PROFILES or len(cls.SENDER_PROFILES) == 0:
            errors.append("No sender profiles configured")

        # Apollo API key is optional but recommended for enrichment
        if not cls.APOLLO_API_KEY:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("APOLLO_API_KEY not set - enrichment features will be unavailable")

        if errors:
            raise ValueError(
                "Configuration errors:\n" + "\n".join(f"- {e}" for e in errors)
            )

        return True

    @classmethod
    def get_sender_profile(cls, index: int = 0):
        """Get a sender profile by index (for rotation)"""
        return cls.SENDER_PROFILES[index % len(cls.SENDER_PROFILES)]
