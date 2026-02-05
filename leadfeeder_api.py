"""
Leadfeeder API Client

Official API integration to fetch visitor data from Leadfeeder.
Replaces the Selenium-based scraper with reliable API calls.

API Documentation: https://docs.leadfeeder.com/api/
"""

import logging
import requests
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from config import Config
from lead_registry import get_connection, utc_now

logger = logging.getLogger(__name__)


class LeadfeederAPI:
    """Client for Leadfeeder API v2."""

    BASE_URL = "https://api.leadfeeder.com"

    def __init__(self, api_token: str = None):
        """
        Initialize Leadfeeder API client.

        Args:
            api_token: Leadfeeder API token (defaults to Config.LEADFEEDER_API_KEY)
        """
        self.api_token = api_token or Config.LEADFEEDER_API_KEY
        if not self.api_token:
            raise ValueError("Leadfeeder API token not configured")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token token={self.api_token}",
            "User-Agent": "PersonalizedOutreach/1.0",
            "Accept": "application/json"
        })

        # Rate limiting: 100 requests per minute
        self.rate_limit = 100
        self.rate_limit_window = 60  # seconds
        self.request_times = []

    def _rate_limit_check(self):
        """Enforce rate limiting (100 requests per minute)."""
        now = time.time()

        # Remove requests older than the time window
        self.request_times = [t for t in self.request_times if now - t < self.rate_limit_window]

        # If at limit, wait until oldest request expires
        if len(self.request_times) >= self.rate_limit:
            sleep_time = self.rate_limit_window - (now - self.request_times[0]) + 0.1
            if sleep_time > 0:
                logger.info(f"Rate limit reached, waiting {sleep_time:.1f}s")
                time.sleep(sleep_time)
                # Re-clean after waiting
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < self.rate_limit_window]

        # Record this request
        self.request_times.append(now)

    def _request(self, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
        """
        Make an API request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data

        Returns:
            Response JSON data

        Raises:
            requests.HTTPError: On API errors
        """
        self._rate_limit_check()

        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning("Rate limit exceeded, waiting 60s before retry")
                time.sleep(60)
                return self._request(method, endpoint, params, json_data)
            elif e.response.status_code == 401:
                logger.error("Leadfeeder API authentication failed - check API token")
                raise ValueError("Invalid Leadfeeder API token")
            else:
                logger.error(f"Leadfeeder API error: {e.response.status_code} - {e.response.text}")
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Leadfeeder API request failed: {e}")
            raise

    def get_accounts(self) -> List[Dict]:
        """
        Get all accessible Leadfeeder accounts.

        Returns:
            List of account dictionaries with id, name, timezone, etc.
        """
        logger.info("Fetching Leadfeeder accounts")
        response = self._request("GET", "/accounts")

        accounts = response.get("data", [])
        logger.info(f"Found {len(accounts)} Leadfeeder account(s)")

        return accounts

    def get_account(self, account_id: str) -> Dict:
        """
        Get specific account details.

        Args:
            account_id: Leadfeeder account ID

        Returns:
            Account dictionary
        """
        logger.info(f"Fetching account details for {account_id}")
        response = self._request("GET", f"/accounts/{account_id}")
        return response.get("data", {})

    def get_leads(
        self,
        account_id: str,
        start_date: str = None,
        end_date: str = None,
        page_size: int = 100,
        max_pages: int = None
    ) -> List[Dict]:
        """
        Get leads (companies) for an account within a date range.

        Args:
            account_id: Leadfeeder account ID
            start_date: Start date (YYYY-MM-DD format). Defaults to 7 days ago.
            end_date: End date (YYYY-MM-DD format). Defaults to today.
            page_size: Number of results per page (default: 100, max: 100)
            max_pages: Maximum number of pages to fetch (default: unlimited)

        Returns:
            List of lead dictionaries with company info and visit data
        """
        # Default date range: last 7 days
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        logger.info(f"Fetching leads for account {account_id} from {start_date} to {end_date}")

        all_leads = []
        page_number = 1

        while True:
            if max_pages and page_number > max_pages:
                logger.info(f"Reached max pages limit ({max_pages})")
                break

            params = {
                "start_date": start_date,
                "end_date": end_date,
                "page[size]": page_size,
                "page[number]": page_number
            }

            logger.info(f"Fetching page {page_number} (size: {page_size})")
            response = self._request("GET", f"/accounts/{account_id}/leads", params=params)

            leads = response.get("data", [])
            if not leads:
                logger.info(f"No more leads on page {page_number}")
                break

            all_leads.extend(leads)
            logger.info(f"Retrieved {len(leads)} leads (total: {len(all_leads)})")

            # Check if there are more pages
            links = response.get("links", {})
            if not links.get("next"):
                logger.info("No more pages available")
                break

            page_number += 1

        logger.info(f"Fetched total of {len(all_leads)} leads")
        return all_leads

    def get_lead(self, account_id: str, lead_id: str) -> Dict:
        """
        Get specific lead details.

        Args:
            account_id: Leadfeeder account ID
            lead_id: Lead ID

        Returns:
            Lead dictionary with detailed information
        """
        logger.info(f"Fetching lead {lead_id} from account {account_id}")
        response = self._request("GET", f"/accounts/{account_id}/leads/{lead_id}")
        return response.get("data", {})

    def get_visits(
        self,
        account_id: str,
        start_date: str = None,
        end_date: str = None,
        lead_id: str = None,
        page_size: int = 100,
        max_pages: int = None
    ) -> List[Dict]:
        """
        Get visits for an account or specific lead.

        Args:
            account_id: Leadfeeder account ID
            start_date: Start date (YYYY-MM-DD format). Defaults to 7 days ago.
            end_date: End date (YYYY-MM-DD format). Defaults to today.
            lead_id: Optional lead ID to filter visits for specific lead
            page_size: Number of results per page (default: 100, max: 100)
            max_pages: Maximum number of pages to fetch (default: unlimited)

        Returns:
            List of visit dictionaries
        """
        # Default date range: last 7 days
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        if lead_id:
            endpoint = f"/accounts/{account_id}/leads/{lead_id}/visits"
            logger.info(f"Fetching visits for lead {lead_id} from {start_date} to {end_date}")
        else:
            endpoint = f"/accounts/{account_id}/visits"
            logger.info(f"Fetching all visits for account {account_id} from {start_date} to {end_date}")

        all_visits = []
        page_number = 1

        while True:
            if max_pages and page_number > max_pages:
                logger.info(f"Reached max pages limit ({max_pages})")
                break

            params = {
                "start_date": start_date,
                "end_date": end_date,
                "page[size]": page_size,
                "page[number]": page_number
            }

            logger.info(f"Fetching page {page_number} (size: {page_size})")
            response = self._request("GET", endpoint, params=params)

            visits = response.get("data", [])
            if not visits:
                logger.info(f"No more visits on page {page_number}")
                break

            all_visits.extend(visits)
            logger.info(f"Retrieved {len(visits)} visits (total: {len(all_visits)})")

            # Check if there are more pages
            links = response.get("links", {})
            if not links.get("next"):
                logger.info("No more pages available")
                break

            page_number += 1

        logger.info(f"Fetched total of {len(all_visits)} visits")
        return all_visits

    def get_custom_feeds(self, account_id: str) -> List[Dict]:
        """
        Get custom feeds for an account.

        Args:
            account_id: Leadfeeder account ID

        Returns:
            List of custom feed dictionaries
        """
        logger.info(f"Fetching custom feeds for account {account_id}")
        response = self._request("GET", f"/accounts/{account_id}/custom-feeds")
        feeds = response.get("data", [])
        logger.info(f"Found {len(feeds)} custom feed(s)")
        return feeds


def sync_leadfeeder_data(days_back: int = 7, account_id: str = None) -> dict:
    """
    Sync data from Leadfeeder API to local database.

    This replaces the scrape_leadfeeder() function with API-based data fetching.

    Args:
        days_back: Number of days to look back for leads (default: 7)
        account_id: Optional specific account ID (auto-detects if not provided)

    Returns:
        Dictionary with sync results (success, leads_synced, etc.)
    """
    logger.info(f"Starting Leadfeeder API sync (last {days_back} days)")

    try:
        api = LeadfeederAPI()

        # Get account ID if not provided
        if not account_id:
            accounts = api.get_accounts()
            if not accounts:
                logger.error("No Leadfeeder accounts found")
                return {"success": False, "error": "no_accounts", "leads_synced": 0}

            # Use first account
            account_id = accounts[0].get("id")
            account_name = accounts[0].get("attributes", {}).get("name", "Unknown")
            logger.info(f"Using account: {account_name} (ID: {account_id})")

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        # Fetch leads
        leads = api.get_leads(
            account_id=account_id,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )

        logger.info(f"Retrieved {len(leads)} leads from API")

        # Store in database
        stored_count = store_leadfeeder_api_data(leads)

        # Update integration status
        with get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO integration_status
                (integration_name, status, last_sync_at, error_message, config_valid)
                VALUES (?, ?, ?, ?, ?)
            """, ("leadfeeder", "active", utc_now(), None, 1))

        logger.info(f"Leadfeeder API sync complete: {stored_count} leads stored")

        return {
            "success": True,
            "leads_synced": len(leads),
            "leads_stored": stored_count,
            "account_id": account_id,
            "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        }

    except Exception as e:
        logger.error(f"Leadfeeder API sync failed: {e}", exc_info=True)

        # Update integration status with error
        with get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO integration_status
                (integration_name, status, last_sync_at, error_message, config_valid)
                VALUES (?, ?, ?, ?, ?)
            """, ("leadfeeder", "error", utc_now(), str(e), 0))

        return {"success": False, "error": str(e), "leads_synced": 0}


def store_leadfeeder_api_data(leads: List[Dict]) -> int:
    """
    Store leads from Leadfeeder API into database.

    Args:
        leads: List of lead dictionaries from API

    Returns:
        Number of leads stored
    """
    now = utc_now()
    stored_count = 0

    with get_connection() as conn:
        for lead in leads:
            try:
                # Extract lead attributes
                lead_id = lead.get("id")
                attributes = lead.get("attributes", {})

                company_name = attributes.get("name")
                industry = attributes.get("industry")
                employee_count = attributes.get("employee_count")
                first_visit = attributes.get("first_visit_date")
                last_visit = attributes.get("last_visit_date")
                visit_count = attributes.get("visits", 0)
                quality = attributes.get("quality")

                # Try to extract domain from relationships or included data
                # The API may include website info in relationships
                domain = None
                relationships = lead.get("relationships", {})
                location = relationships.get("location", {}).get("data", {})
                location_attrs = location.get("attributes", {}) if isinstance(location, dict) else {}

                # Generate unique Leadfeeder ID
                leadfeeder_id = f"lf_api_{lead_id}"

                # Calculate expiry (Leadfeeder free tier: 7 days)
                expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

                # Store in leadfeeder_visits table
                conn.execute("""
                    INSERT OR REPLACE INTO leadfeeder_visits (
                        leadfeeder_id, company_name, domain, industry,
                        employee_count, country, page_views, visit_duration,
                        first_visit_at, last_visit_at, pages_visited,
                        referrer, scraped_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    leadfeeder_id,
                    company_name,
                    domain,
                    industry,
                    employee_count,
                    location_attrs.get("country"),
                    visit_count,
                    None,  # visit_duration not in basic API response
                    first_visit,
                    last_visit,
                    "[]",  # pages_visited - would need separate visits API call
                    None,  # referrer
                    now,
                    expires_at
                ))

                # Sync to visitor_companies if we have enough info
                if company_name and (domain or company_name):
                    # Generate company key
                    company_key = domain.replace(".", "_").replace("-", "_") if domain else company_name.lower().replace(" ", "_")

                    # Check if company exists
                    existing = conn.execute("""
                        SELECT company_key, total_visits FROM visitor_companies
                        WHERE company_key = ? OR company_name = ?
                    """, (company_key, company_name)).fetchone()

                    if existing:
                        # Update existing
                        conn.execute("""
                            UPDATE visitor_companies
                            SET total_visits = total_visits + ?,
                                last_visit_at = ?,
                                source = 'leadfeeder',
                                industry = COALESCE(?, industry),
                                employee_count = COALESCE(?, employee_count),
                                country = COALESCE(?, country)
                            WHERE company_key = ?
                        """, (
                            visit_count, last_visit,
                            industry, employee_count,
                            location_attrs.get("country"),
                            existing["company_key"]
                        ))
                    else:
                        # Insert new
                        conn.execute("""
                            INSERT INTO visitor_companies (
                                company_key, company_name, domain, source,
                                industry, employee_count, country,
                                total_visits, first_visit_at, last_visit_at,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, 'leadfeeder', ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            company_key, company_name, domain,
                            industry, employee_count,
                            location_attrs.get("country"), visit_count,
                            first_visit or now, last_visit, now, now
                        ))

                stored_count += 1

            except Exception as e:
                logger.error(f"Failed to store lead {lead.get('id')}: {e}", exc_info=True)

    logger.info(f"Stored {stored_count} leads from Leadfeeder API")
    return stored_count


def get_leadfeeder_status() -> dict:
    """Get current Leadfeeder integration status."""
    try:
        api = LeadfeederAPI()
        accounts = api.get_accounts()
        api_working = True
        account_info = accounts[0] if accounts else None
    except Exception as e:
        logger.error(f"Failed to check Leadfeeder API status: {e}")
        api_working = False
        account_info = None

    with get_connection() as conn:
        status_row = conn.execute("""
            SELECT * FROM integration_status WHERE integration_name = 'leadfeeder'
        """).fetchone()

        company_count = conn.execute("""
            SELECT COUNT(*) as count FROM leadfeeder_visits
            WHERE expires_at > datetime('now')
        """).fetchone()["count"]

        expiring_soon = conn.execute("""
            SELECT COUNT(*) as count FROM leadfeeder_visits
            WHERE expires_at > datetime('now')
            AND expires_at < datetime('now', '+2 days')
        """).fetchone()["count"]

    return {
        "configured": bool(Config.LEADFEEDER_API_KEY),
        "api_working": api_working,
        "account_info": account_info,
        "status": dict(status_row) if status_row else None,
        "active_companies": company_count,
        "expiring_soon": expiring_soon
    }
