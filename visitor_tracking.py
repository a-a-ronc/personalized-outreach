"""
Website Visitor Tracking Module

Core functionality for capturing and storing website visitor data.
Includes rate limiting and session management.
"""

import logging
import uuid
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from threading import Lock

from config import Config
from lead_registry import get_connection, utc_now, normalize_domain

logger = logging.getLogger(__name__)

# In-memory rate limiting (per IP)
_rate_limit_cache = defaultdict(list)
_rate_limit_lock = Lock()


def _clean_old_requests(ip_address: str, window_hours: int = 1):
    """Remove requests older than the rate limit window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    with _rate_limit_lock:
        _rate_limit_cache[ip_address] = [
            ts for ts in _rate_limit_cache[ip_address]
            if ts > cutoff
        ]


def is_rate_limited(ip_address: str) -> bool:
    """Check if an IP address has exceeded the rate limit."""
    _clean_old_requests(ip_address)
    with _rate_limit_lock:
        return len(_rate_limit_cache[ip_address]) >= Config.VISITOR_RATE_LIMIT_PER_HOUR


def record_rate_limit_hit(ip_address: str):
    """Record a request for rate limiting purposes."""
    with _rate_limit_lock:
        _rate_limit_cache[ip_address].append(datetime.now(timezone.utc))


def generate_visit_id() -> str:
    """Generate a unique visit ID."""
    return str(uuid.uuid4())


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def record_visit(
    ip_address: str,
    page_url: str,
    referrer: str = "",
    user_agent: str = "",
    session_id: str = None
) -> dict:
    """
    Record a website visit.

    Args:
        ip_address: Visitor's IP address
        page_url: URL of the visited page
        referrer: HTTP referrer header
        user_agent: User agent string
        session_id: Optional session ID (generated if not provided)

    Returns:
        dict with visit_id, session_id, and status
    """
    # Check rate limit
    if is_rate_limited(ip_address):
        logger.warning(f"Rate limit exceeded for IP: {ip_address}")
        return {
            "success": False,
            "error": "rate_limited",
            "message": "Too many requests from this IP"
        }

    # Record the request for rate limiting
    record_rate_limit_hit(ip_address)

    # Generate IDs
    visit_id = generate_visit_id()
    if not session_id:
        session_id = generate_session_id()

    now = utc_now()

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO visitor_raw (
                    visit_id, ip_address, user_agent, page_url,
                    referrer, session_id, timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                visit_id,
                ip_address,
                user_agent,
                page_url,
                referrer,
                session_id,
                now,
                now
            ))

        logger.info(f"Recorded visit: {visit_id} from {ip_address}")

        return {
            "success": True,
            "visit_id": visit_id,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Failed to record visit: {e}")
        return {
            "success": False,
            "error": "database_error",
            "message": str(e)
        }


def get_visits_by_ip(ip_address: str, limit: int = 100) -> list:
    """Get all visits from a specific IP address."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM visitor_raw
            WHERE ip_address = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (ip_address, limit)).fetchall()
    return [dict(row) for row in rows]


def get_visits_by_session(session_id: str) -> list:
    """Get all visits from a specific session."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM visitor_raw
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,)).fetchall()
    return [dict(row) for row in rows]


def get_recent_visits(hours: int = 24, limit: int = 500) -> list:
    """Get visits from the last N hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM visitor_raw
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
    return [dict(row) for row in rows]


def get_unique_ips_since(hours: int = 24) -> list:
    """Get unique IP addresses from the last N hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT ip_address,
                   COUNT(*) as visit_count,
                   MIN(timestamp) as first_visit,
                   MAX(timestamp) as last_visit
            FROM visitor_raw
            WHERE timestamp >= ?
            GROUP BY ip_address
            ORDER BY visit_count DESC
        """, (cutoff,)).fetchall()
    return [dict(row) for row in rows]


def aggregate_session_data(session_id: str) -> dict:
    """
    Aggregate all visits in a session into a summary.

    Returns:
        dict with session stats: page_count, pages, duration, etc.
    """
    visits = get_visits_by_session(session_id)

    if not visits:
        return None

    pages = [v["page_url"] for v in visits]

    # Calculate duration
    first_visit = visits[0]["timestamp"]
    last_visit = visits[-1]["timestamp"]

    try:
        start = datetime.fromisoformat(first_visit.replace("Z", "+00:00"))
        end = datetime.fromisoformat(last_visit.replace("Z", "+00:00"))
        duration_seconds = int((end - start).total_seconds())
    except:
        duration_seconds = 0

    return {
        "session_id": session_id,
        "ip_address": visits[0]["ip_address"],
        "user_agent": visits[0]["user_agent"],
        "referrer": visits[0].get("referrer", ""),
        "page_count": len(pages),
        "pages": pages,
        "duration_seconds": duration_seconds,
        "started_at": first_visit,
        "ended_at": last_visit
    }


def get_unresolved_ips(limit: int = 100) -> list:
    """
    Get IP addresses that haven't been resolved to companies yet.

    Returns IPs from visitor_raw that don't have entries in visitor_ip_resolution.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT vr.ip_address,
                   COUNT(*) as visit_count,
                   MAX(vr.timestamp) as last_visit
            FROM visitor_raw vr
            LEFT JOIN visitor_ip_resolution vir ON vr.ip_address = vir.ip_address
            WHERE vir.ip_address IS NULL
            GROUP BY vr.ip_address
            ORDER BY visit_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(row) for row in rows]


def cleanup_old_visits(days: int = None):
    """
    Remove visits older than the retention period.

    Args:
        days: Number of days to retain (defaults to Config.VISITOR_DATA_RETENTION_DAYS)
    """
    if days is None:
        days = Config.VISITOR_DATA_RETENTION_DAYS

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    with get_connection() as conn:
        result = conn.execute("""
            DELETE FROM visitor_raw WHERE timestamp < ?
        """, (cutoff,))
        deleted = result.rowcount

    logger.info(f"Cleaned up {deleted} visits older than {days} days")
    return deleted


def get_visitor_stats() -> dict:
    """Get overall visitor tracking statistics."""
    with get_connection() as conn:
        # Total visits
        total_visits = conn.execute(
            "SELECT COUNT(*) as count FROM visitor_raw"
        ).fetchone()["count"]

        # Unique IPs
        unique_ips = conn.execute(
            "SELECT COUNT(DISTINCT ip_address) as count FROM visitor_raw"
        ).fetchone()["count"]

        # Visits today
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        visits_today = conn.execute(
            "SELECT COUNT(*) as count FROM visitor_raw WHERE timestamp >= ?",
            (today_start,)
        ).fetchone()["count"]

        # Visits this week
        week_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        visits_week = conn.execute(
            "SELECT COUNT(*) as count FROM visitor_raw WHERE timestamp >= ?",
            (week_start,)
        ).fetchone()["count"]

        # Resolved IPs count
        resolved_ips = conn.execute(
            "SELECT COUNT(DISTINCT ip_address) as count FROM visitor_ip_resolution"
        ).fetchone()["count"]

        # Identified companies count
        identified_companies = conn.execute(
            "SELECT COUNT(*) as count FROM visitor_companies"
        ).fetchone()["count"]

    return {
        "total_visits": total_visits,
        "unique_ips": unique_ips,
        "visits_today": visits_today,
        "visits_this_week": visits_week,
        "resolved_ips": resolved_ips,
        "identified_companies": identified_companies,
        "identification_rate": round(resolved_ips / unique_ips * 100, 1) if unique_ips > 0 else 0
    }
