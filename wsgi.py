"""
Production WSGI entry point for Railway deployment.
This file initializes the Flask app and ensures all startup tasks run.
"""
import os
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the Flask app
from backend.app import app, ensure_seed_data, init_visitor_scheduler

# Initialize on module load (when gunicorn imports this)
logger.info("Initializing application for production...")

try:
    ensure_seed_data()
    logger.info("Seed data initialized")
except Exception as e:
    logger.error(f"Failed to initialize seed data: {e}")

try:
    init_visitor_scheduler()
    logger.info("Visitor tracking scheduler initialized")
except Exception as e:
    logger.error(f"Failed to initialize scheduler: {e}")

logger.info("Application ready")

# This is what gunicorn will import
if __name__ == "__main__":
    # For local testing with gunicorn
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port)
