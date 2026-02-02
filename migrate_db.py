#!/usr/bin/env python3
"""
Database migration script to upgrade schema to v3.
Adds support for sequence templates, multi-channel sequences, signatures, and enhanced tracking.
"""

from lead_registry import init_db, upgrade_schema_v2, upgrade_schema_v3, upgrade_schema_v4, upgrade_schema_v5, upgrade_schema_v6, upgrade_schema_v7, upgrade_schema_v8
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

    # Upgrade to v3
    logger.info("Upgrading to schema v3...")
    upgrade_schema_v3()

    # Upgrade to v4
    logger.info("Upgrading to schema v4...")
    upgrade_schema_v4()

    # Upgrade to v5
    logger.info("Upgrading to schema v5...")
    upgrade_schema_v5()

    # Upgrade to v6
    logger.info("Upgrading to schema v6...")
    upgrade_schema_v6()

    # Upgrade to v7
    logger.info("Upgrading to schema v7...")
    upgrade_schema_v7()

    # Upgrade to v8
    logger.info("Upgrading to schema v8...")
    upgrade_schema_v8()

    logger.info("✓ Database migration completed successfully!")
    logger.info("")
    logger.info("New features available:")
    logger.info("  - Sequence templates library with 4 pre-built templates")
    logger.info("  - Multi-channel sequences (email, call, LinkedIn)")
    logger.info("  - Editable sender signatures with persona context")
    logger.info("  - Sequence settings (personalization mode, signature toggle)")
    logger.info("  - Enhanced lead tracking (LinkedIn status, call attempts)")
    logger.info("  - Sequence orchestration")
    logger.info("  - Unified inbox for all channel activity")
    logger.info("  - Email warmup and ramp-up settings per sender")
    logger.info("  - Sender analytics with drill-down by category")
    logger.info("  - Comprehensive sender management dashboard")
    logger.info("  - Website visitor identification (DIY + Leadfeeder)")
    logger.info("  - IP-to-company resolution with MaxMind GeoLite2")
    logger.info("  - Visitor analytics and company tracking")
    logger.info("  - Email warmup system with gradual ramp-up")
    logger.info("  - Daily send limits per sender (conservative/moderate/aggressive)")
    logger.info("  - Warmup tracking and progress monitoring")


if __name__ == "__main__":
    main()
