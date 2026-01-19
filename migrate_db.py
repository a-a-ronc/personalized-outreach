#!/usr/bin/env python3
"""
Database migration script to upgrade schema to v2.
Adds support for multi-channel sequences, signatures, and enhanced tracking.
"""

from lead_registry import init_db, upgrade_schema_v2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting database migration...")

    # Ensure base tables exist
    logger.info("Initializing base schema...")
    init_db()

    # Upgrade to v2
    logger.info("Upgrading to schema v2...")
    upgrade_schema_v2()

    logger.info("✓ Database migration completed successfully!")
    logger.info("")
    logger.info("New features available:")
    logger.info("  - Multi-channel sequences (email, call, LinkedIn)")
    logger.info("  - Signature management")
    logger.info("  - Enhanced lead tracking (LinkedIn status, call attempts)")
    logger.info("  - Sequence orchestration")


if __name__ == "__main__":
    main()
