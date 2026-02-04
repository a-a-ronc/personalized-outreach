"""
Leadfeeder Scraper Module

Selenium-based automation to scrape visitor data from Leadfeeder's free tier.
Designed to capture data before the 7-day expiration window.
"""

import logging
import time
import random
import json
import re
from datetime import datetime, timezone, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config import Config
from lead_registry import get_connection, utc_now

logger = logging.getLogger(__name__)


class LeadfeederScraper:
    """Scrapes visitor data from Leadfeeder dashboard."""

    # Leadfeeder is now Dealfront (acquired/merged)
    LEADFEEDER_LOGIN_URL = "https://app.dealfront.com/login"
    LEADFEEDER_DASHBOARD_URL = "https://app.dealfront.com"

    def __init__(self, email: str = None, password: str = None):
        self.email = email or Config.LEADFEEDER_EMAIL
        self.password = password or Config.LEADFEEDER_PASSWORD
        self.driver = None
        self.feed_id = None  # Will be set after login

    def init_driver(self, headless: bool = True):
        """Initialize Chrome driver with anti-detection measures."""
        import os
        import shutil

        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")  # Required for headless mode
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Check if running on Railway/Nixpacks with chromium
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        if chromium_path:
            chrome_options.binary_location = chromium_path
            logger.info(f"Using Chromium at: {chromium_path}")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })

        logger.info("Chrome driver initialized")

    def _human_delay(self, min_seconds: float = 1, max_seconds: float = 3):
        """Add random delay to mimic human behavior."""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def _type_slowly(self, element, text: str):
        """Type text character by character with random delays and trigger JS events."""
        # Click to focus the field first
        element.click()
        time.sleep(0.1)

        # Clear any existing value
        element.clear()
        time.sleep(0.1)

        # Type character by character
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))

        # Trigger JavaScript events that modern forms expect
        try:
            self.driver.execute_script("""
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
            """, element)
        except Exception as e:
            logger.debug(f"Failed to trigger JS events: {e}")

    def login(self) -> bool:
        """Login to Leadfeeder."""
        if not self.email or not self.password:
            logger.error("Leadfeeder credentials not configured")
            return False

        try:
            logger.info("Navigating to Leadfeeder login page...")
            self.driver.get(self.LEADFEEDER_LOGIN_URL)
            self._human_delay(2, 4)

            # Wait for login form
            logger.info("Waiting for email field...")
            email_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email']"))
            )
            logger.info("Email field found")

            # Find password field
            logger.info("Looking for password field...")
            password_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='password'], input[name='password']")
            logger.info("Password field found")

            # Enter credentials slowly
            logger.info(f"Entering email: {self.email[:3]}...{self.email[-10:]}")
            self._type_slowly(email_field, self.email)
            self._human_delay(0.5, 1)
            logger.info("Entering password...")
            self._type_slowly(password_field, self.password)
            self._human_delay(0.5, 1)
            logger.info("Credentials entered")

            # Find and click login button
            logger.info("Looking for login button...")
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            button_text = login_button.text
            logger.info(f"Login button found: '{button_text}'")
            login_button.click()
            logger.info("Login button clicked, waiting for redirect...")

            # Wait for dashboard to load
            self._human_delay(5, 8)

            # Check if login was successful
            current_url = self.driver.current_url
            # Dealfront uses /sign/in, Leadfeeder used /login
            if "login" not in current_url.lower() and "sign" not in current_url.lower() and "error" not in current_url.lower():
                logger.info(f"Leadfeeder/Dealfront login successful - redirected to: {current_url}")

                # Extract feed ID from Dealfront URL (e.g., https://app.dealfront.com/f/296346/...)
                feed_id_match = re.search(r'/f/(\d+)', current_url)
                if feed_id_match:
                    self.feed_id = feed_id_match.group(1)
                    logger.info(f"Detected feed ID: {self.feed_id}")
                else:
                    # Try old Leadfeeder URL pattern for backwards compatibility
                    old_feed_match = re.search(r'/feeds/([^/]+)', current_url)
                    if old_feed_match:
                        self.feed_id = old_feed_match.group(1)
                        logger.info(f"Detected feed ID (old format): {self.feed_id}")
                    else:
                        logger.warning("Could not detect feed ID from URL, using base dashboard URL")
                        self.feed_id = None

                return True
            else:
                logger.error(f"Leadfeeder/Dealfront login failed - still on login/sign-in page: {current_url}")
                # Check for error messages on page
                try:
                    # Check for various error message patterns
                    error_messages = self.driver.find_elements(By.CSS_SELECTOR, "[role='alert'], .error, .alert-error, .alert-danger, [class*='error'], [class*='alert']")
                    if error_messages:
                        logger.info(f"Found {len(error_messages)} potential error elements")
                        for i, msg in enumerate(error_messages):
                            text = msg.text.strip() if msg.text else ""
                            if text:
                                logger.error(f"Error message {i+1}: {text}")
                    else:
                        logger.warning("No error messages found on page")

                    # Log page title and a snippet of body text
                    page_title = self.driver.title
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                    logger.info(f"Page title: {page_title}")
                    logger.info(f"Page content preview: {body_text}")
                except Exception as e:
                    logger.warning(f"Failed to retrieve page info: {e}")
                return False

        except TimeoutException:
            logger.error("Leadfeeder login timed out")
            return False
        except Exception as e:
            logger.error(f"Leadfeeder login error: {e}")
            return False

    def scrape_visitors(self, max_companies: int = 100) -> list:
        """
        Scrape visitor companies from Leadfeeder dashboard.

        Args:
            max_companies: Maximum number of companies to scrape

        Returns:
            List of company dictionaries
        """
        companies = []

        try:
            # Navigate to visitors/companies page
            logger.info("Navigating to Dealfront/Leadfeeder visitors page...")

            # Construct visitors URL with feed ID if available
            if hasattr(self, 'feed_id') and self.feed_id:
                # New Dealfront URL structure
                visitors_url = f"{self.LEADFEEDER_DASHBOARD_URL}/f/{self.feed_id}/feed/all-companies"
            else:
                # Fallback: try to detect current URL structure
                current_url = self.driver.current_url
                if '/f/' in current_url:
                    # Dealfront URL: replace page with /feed/all-companies
                    visitors_url = re.sub(r'/f/\d+/[^?]*', lambda m: f"/f/{m.group(0).split('/')[2]}/feed/all-companies", current_url)
                elif '/feeds/' in current_url:
                    # Old Leadfeeder URL
                    visitors_url = re.sub(r'/feeds/[^/]+/[^/?]*', lambda m: m.group(0).rsplit('/', 1)[0] + '/visitors', current_url)
                else:
                    # Last resort: use base URL (likely won't work without feed ID)
                    visitors_url = f"{self.LEADFEEDER_DASHBOARD_URL}/feed/all-companies"

            logger.info(f"Navigating to: {visitors_url}")
            self.driver.get(visitors_url)
            self._human_delay(3, 5)

            # Scroll to load more companies (lazy loading)
            self._scroll_and_load(max_companies)

            # Try multiple selector strategies to handle Leadfeeder UI changes
            selector_strategies = [
                # Card-based layout selectors (current Leadfeeder UI)
                "[role='button'][class*='company']",  # Clickable company cards
                "div[class*='CompanyCard']",  # Company card divs
                "div[class*='company-item']",  # Company item divs
                "div[class*='CompanyListItem']",  # List item pattern
                "article",  # Semantic article elements
                "li[class*='company']",  # List items with company class
                "div[role='button']",  # Generic clickable divs (very broad)
                # Table-based selectors (older UI)
                "table tbody tr",  # Generic table rows
                "[role='row']",  # ARIA table rows
                ".MuiTableRow-root",  # Material UI table rows
                # Original selectors
                "[data-testid='company-row'], .company-row, .visitor-row",
                "tr[class*='company'], tr[class*='visitor']",
                # Alternative selectors
                ".leads-list-item, .lead-item",
                "[class*='LeadRow'], [class*='CompanyRow']",
                # Very generic fallback
                "ul > li",  # Any list items
                "div[class*='list'] > div[class*='item']"
            ]

            company_elements = []
            for selector in selector_strategies:
                company_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if company_elements:
                    logger.info(f"Found {len(company_elements)} elements using selector: {selector}")
                    break

            if not company_elements:
                # Debug: Log page source to understand structure
                logger.warning("No company elements found with any selector")
                try:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                    logger.warning(f"Page content preview: {page_text}")

                    # Try to find any clickable elements to understand structure
                    all_buttons = self.driver.find_elements(By.CSS_SELECTOR, "[role='button']")
                    logger.warning(f"Found {len(all_buttons)} clickable elements on page")

                    # Log some element classes for debugging
                    if all_buttons:
                        for i, btn in enumerate(all_buttons[:5]):
                            classes = btn.get_attribute("class")
                            text = btn.text[:50] if btn.text else "(no text)"
                            logger.warning(f"Button {i}: class='{classes}' text='{text}'")
                except Exception as debug_error:
                    logger.warning(f"Failed to retrieve debug info: {debug_error}")

            logger.info(f"Found {len(company_elements)} company elements total")

            for idx, element in enumerate(company_elements[:max_companies]):
                try:
                    company = self._parse_company_element(element, idx)
                    if company:
                        companies.append(company)
                except Exception as e:
                    logger.debug(f"Failed to parse company element {idx}: {e}")

            logger.info(f"Scraped {len(companies)} companies from Leadfeeder")

        except Exception as e:
            logger.error(f"Error scraping visitors: {e}")

        return companies

    def _scroll_and_load(self, target_count: int):
        """Scroll to load more companies via lazy loading."""
        last_height = 0
        loaded_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 20

        while loaded_count < target_count and scroll_attempts < max_scroll_attempts:
            # Scroll down
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self._human_delay(1, 2)

            # Count loaded elements
            elements = self.driver.find_elements(
                By.CSS_SELECTOR,
                "[data-testid='company-row'], .company-row, .visitor-row, .leads-list-item"
            )
            loaded_count = len(elements)

            # Check if we've reached the bottom
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0

            last_height = new_height

        # Scroll back to top
        self.driver.execute_script("window.scrollTo(0, 0);")
        self._human_delay(1, 2)

    def _parse_company_element(self, element, index: int) -> dict:
        """Parse a company element into a structured dict."""
        company = {
            "leadfeeder_id": f"lf_{index}_{datetime.now().strftime('%Y%m%d')}",
            "company_name": None,
            "domain": None,
            "industry": None,
            "employee_count": None,
            "country": None,
            "page_views": None,
            "visit_duration": None,
            "first_visit_at": None,
            "last_visit_at": None,
            "pages_visited": [],
            "referrer": None
        }

        try:
            # Try to get company name
            name_selectors = [
                ".company-name", ".lead-name", "[class*='CompanyName']",
                "h3", "h4", ".name", "[data-testid='company-name']"
            ]
            for selector in name_selectors:
                try:
                    name_el = element.find_element(By.CSS_SELECTOR, selector)
                    company["company_name"] = name_el.text.strip()
                    break
                except NoSuchElementException:
                    continue

            # Try to get domain
            domain_selectors = [
                ".company-domain", ".domain", "[class*='Domain']",
                "a[href*='http']", ".website"
            ]
            for selector in domain_selectors:
                try:
                    domain_el = element.find_element(By.CSS_SELECTOR, selector)
                    domain_text = domain_el.text.strip() or domain_el.get_attribute("href")
                    if domain_text:
                        company["domain"] = self._clean_domain(domain_text)
                    break
                except NoSuchElementException:
                    continue

            # Try to get visit count/page views
            view_selectors = [
                ".page-views", ".visits", "[class*='PageView']",
                "[class*='visits']", ".visit-count"
            ]
            for selector in view_selectors:
                try:
                    views_el = element.find_element(By.CSS_SELECTOR, selector)
                    views_text = views_el.text.strip()
                    company["page_views"] = self._parse_number(views_text)
                    break
                except NoSuchElementException:
                    continue

            # Try to get last visit time
            time_selectors = [
                ".last-visit", ".time", "[class*='Time']",
                ".visit-time", ".timestamp"
            ]
            for selector in time_selectors:
                try:
                    time_el = element.find_element(By.CSS_SELECTOR, selector)
                    company["last_visit_at"] = self._parse_relative_time(time_el.text.strip())
                    break
                except NoSuchElementException:
                    continue

            # Try to get industry
            industry_selectors = [
                ".industry", "[class*='Industry']", ".sector"
            ]
            for selector in industry_selectors:
                try:
                    industry_el = element.find_element(By.CSS_SELECTOR, selector)
                    company["industry"] = industry_el.text.strip()
                    break
                except NoSuchElementException:
                    continue

            # Try to get employee count
            employee_selectors = [
                ".employees", "[class*='Employee']", ".company-size"
            ]
            for selector in employee_selectors:
                try:
                    emp_el = element.find_element(By.CSS_SELECTOR, selector)
                    company["employee_count"] = self._parse_employee_count(emp_el.text.strip())
                    break
                except NoSuchElementException:
                    continue

            # Try to get country
            country_selectors = [
                ".country", "[class*='Country']", ".location"
            ]
            for selector in country_selectors:
                try:
                    country_el = element.find_element(By.CSS_SELECTOR, selector)
                    company["country"] = country_el.text.strip()
                    break
                except NoSuchElementException:
                    continue

        except Exception as e:
            logger.debug(f"Error parsing company element: {e}")

        # Only return if we got at least a name or domain
        if company["company_name"] or company["domain"]:
            return company
        return None

    def _clean_domain(self, domain_text: str) -> str:
        """Extract clean domain from text."""
        if not domain_text:
            return None

        # Remove protocol
        domain = domain_text.replace("https://", "").replace("http://", "")
        # Remove path
        domain = domain.split("/")[0]
        # Remove www
        if domain.startswith("www."):
            domain = domain[4:]

        return domain.lower() if domain else None

    def _parse_number(self, text: str) -> int:
        """Parse a number from text (handles formats like '12', '1.2k', etc)."""
        if not text:
            return None

        text = text.lower().strip()

        # Remove non-numeric characters except k, m, .
        multiplier = 1
        if "k" in text:
            multiplier = 1000
            text = text.replace("k", "")
        elif "m" in text:
            multiplier = 1000000
            text = text.replace("m", "")

        try:
            # Extract number
            match = re.search(r"[\d.]+", text)
            if match:
                return int(float(match.group()) * multiplier)
        except:
            pass

        return None

    def _parse_employee_count(self, text: str) -> int:
        """Parse employee count from text (handles ranges like '10-50')."""
        if not text:
            return None

        # Try to find range pattern
        match = re.search(r"(\d+)\s*[-–]\s*(\d+)", text)
        if match:
            # Return midpoint of range
            low, high = int(match.group(1)), int(match.group(2))
            return (low + high) // 2

        # Try single number
        return self._parse_number(text)

    def _parse_relative_time(self, text: str) -> str:
        """Convert relative time text to ISO timestamp."""
        if not text:
            return None

        text = text.lower().strip()
        now = datetime.now(timezone.utc)

        try:
            if "just now" in text or "now" in text:
                return now.isoformat()
            elif "minute" in text:
                minutes = self._parse_number(text) or 1
                return (now - timedelta(minutes=minutes)).isoformat()
            elif "hour" in text:
                hours = self._parse_number(text) or 1
                return (now - timedelta(hours=hours)).isoformat()
            elif "day" in text:
                days = self._parse_number(text) or 1
                return (now - timedelta(days=days)).isoformat()
            elif "week" in text:
                weeks = self._parse_number(text) or 1
                return (now - timedelta(weeks=weeks)).isoformat()
        except:
            pass

        return None

    def get_company_details(self, company_element_index: int) -> dict:
        """
        Click on a company to get more detailed information.

        Note: This is optional and may not be needed for basic scraping.
        """
        # Implementation depends on Leadfeeder's UI structure
        pass

    def close(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()
            logger.info("Chrome driver closed")


def store_leadfeeder_data(companies: list):
    """Store scraped Leadfeeder data in the database."""
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    stored_count = 0

    with get_connection() as conn:
        for company in companies:
            try:
                # Generate unique ID if not present
                leadfeeder_id = company.get("leadfeeder_id") or f"lf_{company.get('domain', '')}_{now}"

                conn.execute("""
                    INSERT OR REPLACE INTO leadfeeder_visits (
                        leadfeeder_id, company_name, domain, industry,
                        employee_count, country, page_views, visit_duration,
                        first_visit_at, last_visit_at, pages_visited,
                        referrer, scraped_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    leadfeeder_id,
                    company.get("company_name"),
                    company.get("domain"),
                    company.get("industry"),
                    company.get("employee_count"),
                    company.get("country"),
                    company.get("page_views"),
                    company.get("visit_duration"),
                    company.get("first_visit_at"),
                    company.get("last_visit_at"),
                    json.dumps(company.get("pages_visited", [])),
                    company.get("referrer"),
                    now,
                    expires_at
                ))
                stored_count += 1
            except Exception as e:
                logger.error(f"Failed to store company {company.get('company_name')}: {e}")

    logger.info(f"Stored {stored_count} companies from Leadfeeder")
    return stored_count


def scrape_leadfeeder():
    """
    Main function to scrape Leadfeeder data.

    This should be called by the scheduler before data expires.
    """
    logger.info("Starting Leadfeeder scrape...")

    scraper = LeadfeederScraper()

    try:
        scraper.init_driver(headless=True)

        if not scraper.login():
            logger.error("Failed to login to Leadfeeder")
            return {"success": False, "error": "login_failed", "companies_scraped": 0}

        companies = scraper.scrape_visitors(max_companies=100)
        stored_count = store_leadfeeder_data(companies)

        # Update integration status
        with get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO integration_status
                (integration_name, status, last_sync_at, error_message, config_valid)
                VALUES (?, ?, ?, ?, ?)
            """, ("leadfeeder", "active", utc_now(), None, 1))

        return {
            "success": True,
            "companies_scraped": len(companies),
            "companies_stored": stored_count
        }

    except Exception as e:
        logger.error(f"Leadfeeder scrape failed: {e}")

        # Update integration status with error
        with get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO integration_status
                (integration_name, status, last_sync_at, error_message, config_valid)
                VALUES (?, ?, ?, ?, ?)
            """, ("leadfeeder", "error", utc_now(), str(e), 0))

        return {"success": False, "error": str(e), "companies_scraped": 0}

    finally:
        scraper.close()


def get_leadfeeder_status() -> dict:
    """Get current Leadfeeder integration status."""
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
        "configured": bool(Config.LEADFEEDER_EMAIL and Config.LEADFEEDER_PASSWORD),
        "status": dict(status_row) if status_row else None,
        "active_companies": company_count,
        "expiring_soon": expiring_soon
    }
