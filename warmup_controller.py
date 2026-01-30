#!/usr/bin/env python3
"""
Email Warmup Controller

Manages email warmup ramp schedules and enforces daily sending limits.
Tracks warmup progress per sender and records all sends.
"""

import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "leads.db"


class WarmupController:
    """
    Controls email warmup progression and daily send limits.

    Ramp Schedules:
    - conservative: 5 → 50 over 28 days (safest, recommended for new domains)
    - moderate: 10 → 50 over 18 days (balanced approach)
    - aggressive: 20 → 50 over 10 days (faster, higher risk)
    """

    RAMP_SCHEDULES = {
        "conservative": [
            5, 5, 5,           # Days 1-3: 5/day
            10, 10, 10, 10,    # Days 4-7: 10/day
            15, 15, 15,        # Days 8-10: 15/day
            20, 20, 20, 20,    # Days 11-14: 20/day
            25, 25,            # Days 15-16: 25/day
            30, 30,            # Days 17-18: 30/day
            35, 35,            # Days 19-20: 35/day
            40, 40,            # Days 21-22: 40/day
            45, 45,            # Days 23-24: 45/day
            50, 50, 50, 50     # Days 25-28: 50/day (full capacity)
        ],
        "moderate": [
            10, 10,            # Days 1-2: 10/day
            15, 15,            # Days 3-4: 15/day
            20, 20,            # Days 5-6: 20/day
            25, 25,            # Days 7-8: 25/day
            30, 30,            # Days 9-10: 30/day
            35, 35,            # Days 11-12: 35/day
            40, 40,            # Days 13-14: 40/day
            45, 45,            # Days 15-16: 45/day
            50, 50             # Days 17-18: 50/day (full capacity)
        ],
        "aggressive": [
            20,                # Day 1: 20/day
            25,                # Day 2: 25/day
            30,                # Day 3: 30/day
            35,                # Day 4: 35/day
            40,                # Day 5: 40/day
            45,                # Day 6: 45/day
            50, 50, 50, 50     # Days 7-10: 50/day (full capacity)
        ]
    }

    def __init__(self, db_path: str = None):
        """Initialize warmup controller with database path."""
        self.db_path = db_path or str(DB_PATH)

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _utc_now(self) -> str:
        """Get current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    def enable_warmup(
        self,
        sender_email: str,
        ramp_schedule: str = "conservative",
        warmup_service: Optional[str] = None,
        warmup_service_id: Optional[str] = None
    ) -> bool:
        """
        Enable warmup for a sender.

        Args:
            sender_email: Sender email address
            ramp_schedule: Schedule type (conservative/moderate/aggressive)
            warmup_service: Optional service name (e.g., 'mailwarm')
            warmup_service_id: Optional service inbox ID

        Returns:
            True if warmup enabled successfully
        """
        if ramp_schedule not in self.RAMP_SCHEDULES:
            logger.error(f"Invalid ramp schedule: {ramp_schedule}")
            return False

        now = self._utc_now()
        initial_limit = self.RAMP_SCHEDULES[ramp_schedule][0]

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sender_signatures
                SET warmup_enabled = 1,
                    warmup_started_at = ?,
                    warmup_day = 1,
                    ramp_schedule = ?,
                    current_daily_limit = ?,
                    daily_limit = ?,
                    warmup_service = ?,
                    warmup_service_id = ?,
                    last_warmup_check = ?,
                    updated_at = ?
                WHERE email = ?
            """, (
                now, ramp_schedule, initial_limit, initial_limit,
                warmup_service, warmup_service_id, now, now, sender_email
            ))
            conn.commit()

        logger.info(
            f"✓ Warmup enabled for {sender_email}: {ramp_schedule} schedule, "
            f"starting at {initial_limit} emails/day"
        )
        return True

    def disable_warmup(self, sender_email: str) -> bool:
        """
        Disable warmup for a sender (sets to full capacity).

        Args:
            sender_email: Sender email address

        Returns:
            True if warmup disabled successfully
        """
        now = self._utc_now()

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sender_signatures
                SET warmup_enabled = 0,
                    current_daily_limit = 50,
                    daily_limit = 50,
                    updated_at = ?
                WHERE email = ?
            """, (now, sender_email))
            conn.commit()

        logger.info(f"✓ Warmup disabled for {sender_email}")
        return True

    def get_daily_limit(self, sender_email: str) -> int:
        """
        Get current daily send limit for sender based on warmup day.

        Args:
            sender_email: Sender email address

        Returns:
            Daily send limit (50 if warmup disabled)
        """
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT warmup_enabled, warmup_day, current_daily_limit,
                       ramp_schedule, warmup_started_at
                FROM sender_signatures
                WHERE email = ?
            """, (sender_email,)).fetchone()

        if not row:
            logger.warning(f"Sender not found: {sender_email}")
            return 50  # Default full capacity

        if not row["warmup_enabled"]:
            return 50  # Full capacity when warmup disabled

        warmup_day = row["warmup_day"] or 1
        ramp_schedule = row["ramp_schedule"] or "conservative"

        schedule = self.RAMP_SCHEDULES.get(ramp_schedule, self.RAMP_SCHEDULES["conservative"])
        day_index = min(warmup_day - 1, len(schedule) - 1)

        return schedule[day_index]

    def get_sends_today(self, sender_email: str) -> int:
        """
        Count how many emails sent today (warmup + campaign).

        Args:
            sender_email: Sender email address

        Returns:
            Number of emails sent today
        """
        with self._get_connection() as conn:
            # Today in UTC
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            row = conn.execute("""
                SELECT COUNT(*) as count
                FROM warmup_sends
                WHERE sender_email = ? AND sent_at >= ?
            """, (sender_email, today_start)).fetchone()

        return row["count"] if row else 0

    def can_send(self, sender_email: str) -> Tuple[bool, int, int]:
        """
        Check if sender can send more emails today.

        Args:
            sender_email: Sender email address

        Returns:
            Tuple of (can_send, sends_today, daily_limit)
        """
        daily_limit = self.get_daily_limit(sender_email)
        sends_today = self.get_sends_today(sender_email)

        can_send = sends_today < daily_limit

        return (can_send, sends_today, daily_limit)

    def record_send(
        self,
        sender_email: str,
        recipient_email: str = None,
        send_type: str = "campaign"
    ) -> bool:
        """
        Record that an email was sent.

        Args:
            sender_email: Sender email address
            recipient_email: Recipient email (optional, for warmup sends)
            send_type: Type of send ('campaign' or 'warmup')

        Returns:
            True if recorded successfully
        """
        # Get current warmup day
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT warmup_day FROM sender_signatures WHERE email = ?
            """, (sender_email,)).fetchone()

            warmup_day = row["warmup_day"] if row else None

            conn.execute("""
                INSERT INTO warmup_sends
                (sender_email, recipient_email, send_type, warmup_day, sent_at, status)
                VALUES (?, ?, ?, ?, ?, 'sent')
            """, (sender_email, recipient_email, send_type, warmup_day, self._utc_now()))
            conn.commit()

        return True

    def advance_warmup_day(self, sender_email: str) -> Optional[int]:
        """
        Advance sender to next warmup day.
        Should be called once per day per sender.

        Args:
            sender_email: Sender email address

        Returns:
            New warmup day number, or None if failed
        """
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT warmup_enabled, warmup_day, ramp_schedule, warmup_started_at
                FROM sender_signatures
                WHERE email = ?
            """, (sender_email,)).fetchone()

            if not row or not row["warmup_enabled"]:
                return None

            new_day = (row["warmup_day"] or 1) + 1
            ramp_schedule = row["ramp_schedule"] or "conservative"
            schedule = self.RAMP_SCHEDULES.get(ramp_schedule, self.RAMP_SCHEDULES["conservative"])

            # Calculate new daily limit
            day_index = min(new_day - 1, len(schedule) - 1)
            new_limit = schedule[day_index]

            now = self._utc_now()

            conn.execute("""
                UPDATE sender_signatures
                SET warmup_day = ?,
                    current_daily_limit = ?,
                    daily_limit = ?,
                    last_warmup_check = ?,
                    updated_at = ?
                WHERE email = ?
            """, (new_day, new_limit, new_limit, now, now, sender_email))
            conn.commit()

        logger.info(
            f"✓ Advanced {sender_email} to warmup day {new_day} "
            f"(limit: {new_limit} emails/day)"
        )
        return new_day

    def get_warmup_status(self, sender_email: str) -> Optional[Dict]:
        """
        Get current warmup status for sender.

        Args:
            sender_email: Sender email address

        Returns:
            Dictionary with warmup status, or None if sender not found
        """
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT warmup_enabled, warmup_day, current_daily_limit,
                       ramp_schedule, warmup_started_at, warmup_service,
                       warmup_service_id, last_warmup_check
                FROM sender_signatures
                WHERE email = ?
            """, (sender_email,)).fetchone()

        if not row:
            return None

        if not row["warmup_enabled"]:
            return {
                "sender_email": sender_email,
                "warmup_enabled": False,
                "daily_limit": 50,
                "sends_today": self.get_sends_today(sender_email)
            }

        sends_today = self.get_sends_today(sender_email)
        daily_limit = row["current_daily_limit"] or 50

        # Calculate progress
        ramp_schedule = row["ramp_schedule"] or "conservative"
        schedule = self.RAMP_SCHEDULES[ramp_schedule]
        warmup_day = row["warmup_day"] or 1
        total_days = len(schedule)
        progress_percent = min(100, int((warmup_day / total_days) * 100))

        # Calculate days until full capacity
        days_until_full = max(0, total_days - warmup_day)

        return {
            "sender_email": sender_email,
            "warmup_enabled": True,
            "warmup_day": warmup_day,
            "total_days": total_days,
            "progress_percent": progress_percent,
            "ramp_schedule": ramp_schedule,
            "daily_limit": daily_limit,
            "sends_today": sends_today,
            "remaining_today": max(0, daily_limit - sends_today),
            "warmup_started_at": row["warmup_started_at"],
            "warmup_service": row["warmup_service"],
            "warmup_service_id": row["warmup_service_id"],
            "days_until_full": days_until_full,
            "last_check": row["last_warmup_check"]
        }

    def get_all_warmup_senders(self) -> list[Dict]:
        """
        Get all senders with warmup enabled.

        Returns:
            List of sender warmup status dictionaries
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT email
                FROM sender_signatures
                WHERE warmup_enabled = 1
            """).fetchall()

        return [self.get_warmup_status(row["email"]) for row in rows]

    def check_and_advance_warmup(self) -> int:
        """
        Check all senders and advance warmup day if 24+ hours passed.
        Should be called by daily scheduler.

        Returns:
            Number of senders advanced
        """
        advanced_count = 0

        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT email, warmup_day, warmup_started_at, last_warmup_check
                FROM sender_signatures
                WHERE warmup_enabled = 1
            """).fetchall()

        for row in rows:
            sender_email = row["email"]
            last_check = row["last_warmup_check"] or row["warmup_started_at"]

            if not last_check:
                continue

            # Parse last check timestamp
            try:
                last_check_dt = datetime.fromisoformat(last_check.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                logger.warning(f"Invalid timestamp for {sender_email}: {last_check}")
                continue

            # Check if 24+ hours passed
            hours_since_check = (datetime.now(timezone.utc) - last_check_dt).total_seconds() / 3600

            if hours_since_check >= 24:
                result = self.advance_warmup_day(sender_email)
                if result:
                    advanced_count += 1

        if advanced_count > 0:
            logger.info(f"✓ Advanced {advanced_count} sender(s) to next warmup day")

        return advanced_count


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    controller = WarmupController()

    # Enable warmup for a sender
    # controller.enable_warmup("sender@example.com", ramp_schedule="conservative")

    # Check daily limit
    # limit = controller.get_daily_limit("sender@example.com")
    # print(f"Daily limit: {limit}")

    # Check if can send
    # can_send, sent, limit = controller.can_send("sender@example.com")
    # print(f"Can send: {can_send} (sent {sent}/{limit} today)")

    # Get warmup status
    # status = controller.get_warmup_status("sender@example.com")
    # print(status)
