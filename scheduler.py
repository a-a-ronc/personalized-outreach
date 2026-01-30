"""
Background Scheduler Module

APScheduler-based background job scheduler for:
- Email warmup advancement (daily)
- Leadfeeder data scraping (daily)
- IP resolution for new visitors (hourly)
- Data reconciliation (hourly)
- MaxMind database updates (weekly)
- Data cleanup (daily)
"""

import logging
from datetime import datetime, timezone

from config import Config
from lead_registry import get_connection, utc_now

logger = logging.getLogger(__name__)

# Try to import APScheduler, provide fallback if not installed
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not installed. Run: pip install apscheduler")

# Global scheduler instance
scheduler = None


def init_scheduler():
    """Initialize the background scheduler."""
    global scheduler

    if not APSCHEDULER_AVAILABLE:
        logger.error("APScheduler not available. Scheduler will not run.")
        return None

    if not Config.SCHEDULER_ENABLED:
        logger.info("Scheduler is disabled in config")
        return None

    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,  # Combine missed runs
            "max_instances": 1,  # Only one instance of each job
            "misfire_grace_time": 3600  # 1 hour grace time for missed jobs
        }
    )

    # Add jobs
    _add_scheduled_jobs()

    logger.info("Scheduler initialized with jobs")
    return scheduler


def _add_scheduled_jobs():
    """Add all scheduled jobs to the scheduler."""
    global scheduler

    if not scheduler:
        return

    # Email warmup advancement - Daily at midnight UTC
    scheduler.add_job(
        job_warmup_advancement,
        CronTrigger(hour=0, minute=0),
        id="warmup_advancement",
        name="Email Warmup Advancement",
        replace_existing=True
    )

    # Leadfeeder scrape - Daily at 2 AM UTC
    scheduler.add_job(
        job_leadfeeder_scrape,
        CronTrigger(hour=2, minute=0),
        id="leadfeeder_scrape",
        name="Leadfeeder Daily Scrape",
        replace_existing=True
    )

    # IP resolution - Every hour
    scheduler.add_job(
        job_resolve_pending_ips,
        IntervalTrigger(hours=1),
        id="ip_resolution",
        name="Resolve Pending IPs",
        replace_existing=True
    )

    # Data reconciliation - Every 2 hours
    scheduler.add_job(
        job_reconcile_visitors,
        IntervalTrigger(hours=2),
        id="visitor_reconciliation",
        name="Visitor Data Reconciliation",
        replace_existing=True
    )

    # MaxMind database update - Weekly on Sunday at 3 AM UTC
    scheduler.add_job(
        job_update_maxmind,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="maxmind_update",
        name="MaxMind Database Update",
        replace_existing=True
    )

    # Data cleanup - Daily at 4 AM UTC
    scheduler.add_job(
        job_cleanup_old_data,
        CronTrigger(hour=4, minute=0),
        id="data_cleanup",
        name="Old Data Cleanup",
        replace_existing=True
    )

    logger.info("Added 6 scheduled jobs")


def start_scheduler():
    """Start the scheduler if not already running."""
    global scheduler

    if not scheduler:
        init_scheduler()

    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
        return True

    return False


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        return True

    return False


def get_scheduler_status() -> dict:
    """Get current scheduler status and job information."""
    global scheduler

    if not scheduler:
        return {
            "running": False,
            "available": APSCHEDULER_AVAILABLE,
            "enabled": Config.SCHEDULER_ENABLED,
            "jobs": []
        }

    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
            "pending": job.pending
        })

    return {
        "running": scheduler.running,
        "available": APSCHEDULER_AVAILABLE,
        "enabled": Config.SCHEDULER_ENABLED,
        "jobs": jobs
    }


def run_job_now(job_id: str) -> dict:
    """Manually trigger a job to run immediately."""
    global scheduler

    if not scheduler:
        return {"success": False, "error": "Scheduler not initialized"}

    job = scheduler.get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    try:
        # Run the job function directly
        job.func()
        return {"success": True, "job_id": job_id}
    except Exception as e:
        logger.error(f"Manual job execution failed: {e}")
        return {"success": False, "error": str(e)}


def _update_job_status(job_name: str, status: str, error: str = None):
    """Update job status in the database."""
    now = utc_now()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO scheduled_jobs (job_name, last_run_at, status, error, run_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(job_name) DO UPDATE SET
                last_run_at = ?,
                status = ?,
                error = ?,
                run_count = run_count + 1
        """, (job_name, now, status, error, now, status, error))


# Job Functions

def job_warmup_advancement():
    """Job: Advance warmup days for all active senders."""
    logger.info("Starting warmup advancement job...")

    try:
        from warmup_controller import WarmupController
        controller = WarmupController()
        advanced_count = controller.check_and_advance_warmup()

        _update_job_status("warmup_advancement", "success")
        logger.info(f"Warmup advancement completed: {advanced_count} senders advanced")

    except Exception as e:
        _update_job_status("warmup_advancement", "error", str(e))
        logger.error(f"Warmup advancement job error: {e}")


def job_leadfeeder_scrape():
    """Job: Scrape Leadfeeder data."""
    logger.info("Starting scheduled Leadfeeder scrape...")

    try:
        from leadfeeder_scraper import scrape_leadfeeder
        result = scrape_leadfeeder()

        if result.get("success"):
            _update_job_status("leadfeeder_scrape", "success")
            logger.info(f"Leadfeeder scrape completed: {result.get('companies_scraped')} companies")
        else:
            _update_job_status("leadfeeder_scrape", "failed", result.get("error"))
            logger.error(f"Leadfeeder scrape failed: {result.get('error')}")

    except Exception as e:
        _update_job_status("leadfeeder_scrape", "error", str(e))
        logger.error(f"Leadfeeder scrape job error: {e}")


def job_resolve_pending_ips():
    """Job: Resolve unresolved IP addresses."""
    logger.info("Starting IP resolution job...")

    try:
        from ip_resolver import resolve_pending_ips
        resolved_count = resolve_pending_ips(limit=50)

        _update_job_status("ip_resolution", "success")
        logger.info(f"IP resolution completed: {resolved_count} IPs resolved")

    except Exception as e:
        _update_job_status("ip_resolution", "error", str(e))
        logger.error(f"IP resolution job error: {e}")


def job_reconcile_visitors():
    """Job: Reconcile visitor data from all sources."""
    logger.info("Starting visitor reconciliation job...")

    try:
        from visitor_reconciliation import reconcile_visitor_data
        reconciled_count = reconcile_visitor_data()

        _update_job_status("visitor_reconciliation", "success")
        logger.info(f"Visitor reconciliation completed: {reconciled_count} companies processed")

    except Exception as e:
        _update_job_status("visitor_reconciliation", "error", str(e))
        logger.error(f"Visitor reconciliation job error: {e}")


def job_update_maxmind():
    """Job: Update MaxMind GeoLite2 databases."""
    logger.info("Starting MaxMind database update...")

    try:
        from ip_resolver import download_maxmind_databases
        success = download_maxmind_databases()

        if success:
            _update_job_status("maxmind_update", "success")
            logger.info("MaxMind databases updated successfully")
        else:
            _update_job_status("maxmind_update", "failed", "Download failed")
            logger.error("MaxMind database update failed")

    except Exception as e:
        _update_job_status("maxmind_update", "error", str(e))
        logger.error(f"MaxMind update job error: {e}")


def job_cleanup_old_data():
    """Job: Clean up old visitor data."""
    logger.info("Starting data cleanup job...")

    try:
        from visitor_tracking import cleanup_old_visits

        deleted = cleanup_old_visits()
        _update_job_status("data_cleanup", "success")
        logger.info(f"Data cleanup completed: {deleted} old visits removed")

    except Exception as e:
        _update_job_status("data_cleanup", "error", str(e))
        logger.error(f"Data cleanup job error: {e}")


def get_job_history(job_name: str = None, limit: int = 10) -> list:
    """Get job execution history."""
    with get_connection() as conn:
        if job_name:
            rows = conn.execute("""
                SELECT * FROM scheduled_jobs
                WHERE job_name = ?
                ORDER BY last_run_at DESC
                LIMIT ?
            """, (job_name, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM scheduled_jobs
                ORDER BY last_run_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

    return [dict(row) for row in rows]
