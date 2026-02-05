"""
Leadfeeder Scraper Module

⚠️ DEPRECATED ⚠️

This module is DEPRECATED and no longer used. We've migrated to the official Leadfeeder API
for faster, more reliable data extraction.

Use leadfeeder_api.py instead:
- 10x faster (30 seconds vs 3-5 minutes)
- More reliable (no UI changes to break)
- No browser automation required (no Selenium, ChromeDriver, VNC)
- Official API support with rate limiting

This file is kept for reference only.

---

LEGACY CODE BELOW (Selenium-based web scraping)

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
        import platform

        # On Windows, always run in non-headless mode for easy viewing
        is_windows = platform.system() == "Windows"
        if is_windows:
            logger.info("Windows detected - running Chrome in visible mode (no VNC needed)")
            headless = False  # Show browser window directly on Windows
        else:
            # On Linux, try to start VNC for remote viewing
            try:
                from vnc_manager import ensure_vnc_running
                vnc_display = ensure_vnc_running()
                if vnc_display:
                    logger.info(f"VNC enabled - browser will be viewable remotely on display {vnc_display}")
                    headless = False  # Don't use headless mode when VNC is active
            except Exception as e:
                logger.debug(f"VNC not available: {e}")

        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        if headless:
            chrome_options.add_argument("--disable-gpu")  # Only for headless mode
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

    def _take_screenshot(self, name: str):
        """Take a screenshot for debugging."""
        try:
            import os
            screenshot_dir = "/tmp/leadfeeder_screenshots" if os.path.exists("/tmp") else "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            filepath = f"{screenshot_dir}/{name}_{datetime.now().strftime('%H%M%S')}.png"
            self.driver.save_screenshot(filepath)
            logger.info(f"Screenshot saved: {filepath}")
            return filepath
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")

    def _dump_page_html(self, name: str):
        """Dump page HTML for debugging."""
        try:
            import os
            html_dir = "/tmp/leadfeeder_screenshots" if os.path.exists("/tmp") else "screenshots"
            os.makedirs(html_dir, exist_ok=True)
            filepath = f"{html_dir}/{name}_{datetime.now().strftime('%H%M%S')}.html"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"HTML dump saved: {filepath}")
            return filepath
        except Exception as e:
            logger.warning(f"Failed to dump HTML: {e}")

    def _type_slowly(self, element, text: str, field_name: str = "field"):
        """Type text with multiple fallback methods for React forms."""
        logger.info(f"Attempting to enter text into {field_name}...")

        try:
            # Method 1: Scroll into view and ensure element is interactable
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)

            # Wait for element to be clickable
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(element)
            )

            # Click to focus
            element.click()
            time.sleep(random.uniform(0.5, 1.0))

            # Try clearing field first (sometimes needed)
            try:
                element.clear()
                time.sleep(0.3)
            except:
                pass

            # Send keys
            element.send_keys(text)
            time.sleep(random.uniform(0.5, 1.0))

            # Verify text was entered
            value = element.get_attribute("value")
            if value and len(value) > 0:
                logger.info(f"✓ Successfully entered {len(value)} characters into {field_name} via send_keys")
                return True
            else:
                logger.warning(f"send_keys failed for {field_name}, trying JavaScript method...")
                raise Exception("send_keys produced empty value")

        except Exception as e:
            logger.warning(f"Method 1 failed for {field_name}: {e}. Trying JavaScript fallback...")

            # Method 2: Use JavaScript to set value directly
            try:
                # Scroll into view again
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)

                # Set value with JavaScript
                self.driver.execute_script("""
                    arguments[0].focus();
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, element, text)
                time.sleep(random.uniform(0.5, 1.0))

                # Verify
                value = element.get_attribute("value")
                if value and len(value) > 0:
                    logger.info(f"✓ Successfully entered {len(value)} characters into {field_name} via JavaScript")
                    return True
                else:
                    logger.error(f"✗ JavaScript method also failed for {field_name}")
                    return False

            except Exception as js_error:
                logger.error(f"✗ All methods failed for {field_name}: {js_error}")
                return False

    def login(self) -> bool:
        """Login to Leadfeeder."""
        if not self.email or not self.password:
            logger.error("Leadfeeder credentials not configured")
            return False

        try:
            logger.info("Navigating to Dealfront/Leadfeeder login page...")
            self.driver.get(self.LEADFEEDER_LOGIN_URL)
            self._human_delay(3, 5)  # Give page time to fully load

            # Take screenshot of login page
            self._take_screenshot("01_login_page")

            # Dump page HTML for debugging selectors
            self._dump_page_html("01_login_page")

            # Log all input fields on the page for debugging
            all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
            logger.info(f"Found {len(all_inputs)} input elements on the page")
            for i, inp in enumerate(all_inputs[:10]):  # Log first 10 inputs
                inp_type = inp.get_attribute("type")
                inp_name = inp.get_attribute("name")
                inp_id = inp.get_attribute("id")
                inp_placeholder = inp.get_attribute("placeholder")
                logger.info(f"  Input {i+1}: type='{inp_type}', name='{inp_name}', id='{inp_id}', placeholder='{inp_placeholder}'")

            # Wait for email field to be clickable (not just present)
            logger.info("Waiting for email field to be clickable...")
            email_field = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email'], input[name='email']"))
            )

            # Log field details for debugging
            field_id = email_field.get_attribute("id")
            field_name = email_field.get_attribute("name")
            field_placeholder = email_field.get_attribute("placeholder")
            logger.info(f"Email field found - id: '{field_id}', name: '{field_name}', placeholder: '{field_placeholder}'")

            # Wait for password field to be clickable
            logger.info("Waiting for password field to be clickable...")
            password_field = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password'], input[name='password']"))
            )

            # Log password field details
            pwd_id = password_field.get_attribute("id")
            pwd_name = password_field.get_attribute("name")
            pwd_placeholder = password_field.get_attribute("placeholder")
            logger.info(f"Password field found - id: '{pwd_id}', name: '{pwd_name}', placeholder: '{pwd_placeholder}'")

            # Enter email with improved method
            logger.info(f"Entering email: {self.email[:3]}...{self.email[-10:]}")
            email_success = self._type_slowly(email_field, self.email, "email field")

            if not email_success:
                logger.error("Failed to enter email - aborting login")
                self._take_screenshot("ERROR_email_failed")
                return False

            # Verify email was entered
            email_value = email_field.get_attribute("value")
            logger.info(f"Email verification: '{email_value[:3]}...{email_value[-10:] if len(email_value) > 10 else email_value}' (length: {len(email_value)})")

            # Screenshot after email
            self._take_screenshot("02_after_email")

            self._human_delay(0.8, 1.5)  # Pause after email like a human

            # Enter password with improved method
            logger.info("Entering password...")
            password_success = self._type_slowly(password_field, self.password, "password field")

            if not password_success:
                logger.error("Failed to enter password - aborting login")
                self._take_screenshot("ERROR_password_failed")
                return False

            # Verify password was entered
            pwd_value = password_field.get_attribute("value")
            logger.info(f"Password verification: {len(pwd_value)} characters entered")

            # Screenshot after password
            self._take_screenshot("03_after_password")

            self._human_delay(1, 2)  # Pause before clicking login
            logger.info("Credentials entered")

            # Find and click login button
            logger.info("Looking for login button...")

            # Use JavaScript to click to avoid stale element issues
            # The button text changes dynamically to "Logging you in..." which can cause stale element errors
            try:
                login_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
                )
                button_text = login_button.text
                logger.info(f"Login button found: '{button_text}'")

                # Small pause before clicking like a human would
                self._human_delay(0.5, 1)

                # Use JavaScript click to avoid stale element issues
                self.driver.execute_script("arguments[0].click();", login_button)
                logger.info("Login button clicked via JavaScript, waiting for redirect...")
            except Exception as e:
                logger.error(f"Failed to click login button: {e}")
                raise

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

        except TimeoutException as e:
            logger.error(f"Leadfeeder login timed out: {e}")
            self._take_screenshot("ERROR_timeout")
            self._dump_page_html("ERROR_timeout")
            return False
        except Exception as e:
            logger.error(f"Leadfeeder login error: {e}", exc_info=True)
            self._take_screenshot("ERROR_exception")
            self._dump_page_html("ERROR_exception")
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

            # Take screenshot before scrolling
            self._take_screenshot("04_companies_page_before_scroll")

            # Scroll to load more companies (lazy loading)
            self._scroll_and_load(max_companies)

            # Take screenshot after scrolling
            self._take_screenshot("05_companies_page_after_scroll")

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
        logger.info(f"Starting scroll to load up to {target_count} companies...")

        # Find the scrollable container (Dealfront uses a specific scrollable div)
        try:
            # Try to find the main scrollable content area
            scrollable_containers = self.driver.find_elements(By.CSS_SELECTOR,
                "[class*='scroll'], main, [role='main'], .main-content")

            if scrollable_containers:
                logger.info(f"Found {len(scrollable_containers)} potential scrollable containers")
        except:
            pass

        last_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 15

        while scroll_attempts < max_scroll_attempts:
            # Scroll down using multiple methods
            # Method 1: Scroll the main window
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Method 2: Scroll within the main content area
            self.driver.execute_script("""
                const main = document.querySelector('main') || document.querySelector('[role="main"]');
                if (main) {
                    main.scrollTop = main.scrollHeight;
                }
            """)

            # Method 3: Scroll the last company element into view to trigger lazy loading
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, "article")
                if elements:
                    last_element = elements[-1]
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'end'});", last_element)
            except:
                pass

            # Wait for lazy loading
            self._human_delay(3, 4)  # Longer delay for lazy loading

            # Count loaded elements
            elements = []
            for selector in ["article", "[role='button'][class*='company']", "div[class*='CompanyCard']"]:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    break

            loaded_count = len(elements)
            logger.info(f"Scroll attempt {scroll_attempts + 1}: Found {loaded_count} company elements")

            # If count hasn't changed in 3 attempts, we've loaded everything
            if loaded_count == last_count:
                scroll_attempts += 1
            else:
                scroll_attempts = 0  # Reset if we found new elements

            last_count = loaded_count

            # If we've reached the target, stop
            if loaded_count >= target_count:
                logger.info(f"Reached target count of {target_count} companies")
                break

        logger.info(f"Scrolling complete. Final count: {loaded_count} companies")

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
    """Store scraped Leadfeeder data in the database and sync to visitor_companies."""
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    stored_count = 0

    with get_connection() as conn:
        for company in companies:
            try:
                # Generate unique ID if not present
                leadfeeder_id = company.get("leadfeeder_id") or f"lf_{company.get('domain', '')}_{now}"
                domain = company.get("domain")
                company_name = company.get("company_name")

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

                # Also sync to visitor_companies table for frontend display
                if domain and company_name:
                    # Generate company key from domain
                    company_key = domain.replace(".", "_").replace("-", "_")

                    # Check if company already exists
                    existing = conn.execute("""
                        SELECT company_key, total_visits FROM visitor_companies
                        WHERE company_key = ? OR domain = ?
                    """, (company_key, domain)).fetchone()

                    page_views = company.get("page_views") or 1
                    last_visit = company.get("last_visit_at") or now

                    if existing:
                        # Update existing record
                        conn.execute("""
                            UPDATE visitor_companies
                            SET company_name = ?, total_visits = total_visits + ?,
                                last_visit_at = ?, source = 'leadfeeder',
                                industry = COALESCE(?, industry),
                                employee_count = COALESCE(?, employee_count),
                                country = COALESCE(?, country)
                            WHERE company_key = ?
                        """, (
                            company_name, page_views, last_visit,
                            company.get("industry"), company.get("employee_count"),
                            company.get("country"), existing["company_key"]
                        ))
                    else:
                        # Insert new record
                        conn.execute("""
                            INSERT INTO visitor_companies (
                                company_key, company_name, domain, source,
                                industry, employee_count, country,
                                total_visits, first_visit_at, last_visit_at,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, 'leadfeeder', ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            company_key, company_name, domain,
                            company.get("industry"), company.get("employee_count"),
                            company.get("country"), page_views,
                            company.get("first_visit_at") or now, last_visit, now, now
                        ))

                stored_count += 1
            except Exception as e:
                logger.error(f"Failed to store company {company.get('company_name')}: {e}", exc_info=True)

    logger.info(f"Stored {stored_count} companies from Leadfeeder and synced to visitor_companies")
    return stored_count


def scrape_leadfeeder():
    """
    Main function to scrape Leadfeeder data.

    This should be called by the scheduler before data expires.
    """
    import platform

    logger.info("Starting Leadfeeder scrape...")

    scraper = LeadfeederScraper()

    try:
        # On Windows, show browser; on Linux, use headless by default
        is_windows = platform.system() == "Windows"
        scraper.init_driver(headless=not is_windows)

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
