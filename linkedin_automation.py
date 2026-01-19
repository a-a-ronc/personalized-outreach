from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
from config import Config


class LinkedInAutomation:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.driver = None

    def init_driver(self, headless=True):
        """Initialize Chrome driver."""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })

    def login(self):
        """Login to LinkedIn."""
        try:
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(random.uniform(2, 4))

            # Enter credentials
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            password_field = self.driver.find_element(By.ID, "password")

            # Type slowly to mimic human behavior
            for char in self.email:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            time.sleep(random.uniform(0.5, 1))

            for char in self.password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            time.sleep(random.uniform(0.5, 1))

            # Click login
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()

            # Wait for login and check if successful
            time.sleep(5)

            # Check if we're on the feed (successful login)
            if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
                return True
            else:
                # Might have hit a security check
                print("Warning: Login may have triggered security check")
                return False

        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def send_connection_request(self, profile_url, message=""):
        """Send connection request with optional message."""
        try:
            self.driver.get(profile_url)
            time.sleep(random.uniform(3, 5))

            # Scroll to mimic human behavior
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(random.uniform(1, 2))

            # Try to find and click "Connect" button
            try:
                connect_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), 'Connect')]]"))
                )
                connect_button.click()
                time.sleep(random.uniform(2, 3))

                # If message provided, click "Add a note"
                if message:
                    try:
                        add_note_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Add a note')]"))
                        )
                        add_note_button.click()
                        time.sleep(random.uniform(1, 2))

                        # Enter message
                        message_field = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.ID, "custom-message"))
                        )

                        # Type message slowly
                        for char in message:
                            message_field.send_keys(char)
                            time.sleep(random.uniform(0.03, 0.08))

                        time.sleep(random.uniform(1, 2))
                    except:
                        # Note button not found, proceed without note
                        pass

                # Click "Send" button
                send_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), 'Send')]]"))
                )
                send_button.click()

                time.sleep(random.uniform(2, 3))
                return True

            except TimeoutException:
                # Connect button not found - might already be connected or pending
                print(f"Connect button not found for {profile_url}")
                return False

        except Exception as e:
            print(f"Connection request failed: {e}")
            return False

    def send_message_to_connection(self, profile_url, message):
        """Send message to existing connection."""
        try:
            self.driver.get(profile_url)
            time.sleep(random.uniform(3, 5))

            # Click "Message" button
            message_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), 'Message')]]"))
            )
            message_button.click()

            time.sleep(random.uniform(2, 3))

            # Enter message in chat box
            message_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".msg-form__contenteditable, .msg-form__textarea"))
            )

            # Type message slowly
            for char in message:
                message_box.send_keys(char)
                time.sleep(random.uniform(0.03, 0.08))

            time.sleep(random.uniform(1, 2))

            # Click send
            send_button = self.driver.find_element(By.CSS_SELECTOR, ".msg-form__send-button, button[type='submit']")
            send_button.click()

            time.sleep(random.uniform(2, 3))
            return True

        except Exception as e:
            print(f"Message send failed: {e}")
            return False

    def close(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()


# Wrapper functions for sequence_engine.py
def send_connection_request(profile_url, message=""):
    """Send LinkedIn connection request."""
    linkedin_email = getattr(Config, 'LINKEDIN_EMAIL', None)
    linkedin_password = getattr(Config, 'LINKEDIN_PASSWORD', None)

    if not linkedin_email or not linkedin_password:
        raise Exception("LinkedIn credentials not configured in config.py")

    linkedin = LinkedInAutomation(
        email=linkedin_email,
        password=linkedin_password
    )

    try:
        linkedin.init_driver(headless=True)
        login_success = linkedin.login()

        if not login_success:
            linkedin.close()
            return False

        # Random delay before action
        time.sleep(random.uniform(2, 5))

        success = linkedin.send_connection_request(profile_url, message)

        # Random delay after action
        time.sleep(random.uniform(2, 4))

        linkedin.close()
        return success

    except Exception as e:
        print(f"LinkedIn automation error: {e}")
        linkedin.close()
        return False


def send_linkedin_message(profile_url, message):
    """Send LinkedIn message to connection."""
    linkedin_email = getattr(Config, 'LINKEDIN_EMAIL', None)
    linkedin_password = getattr(Config, 'LINKEDIN_PASSWORD', None)

    if not linkedin_email or not linkedin_password:
        raise Exception("LinkedIn credentials not configured")

    linkedin = LinkedInAutomation(
        email=linkedin_email,
        password=linkedin_password
    )

    try:
        linkedin.init_driver(headless=True)
        login_success = linkedin.login()

        if not login_success:
            linkedin.close()
            return False

        time.sleep(random.uniform(2, 5))

        success = linkedin.send_message_to_connection(profile_url, message)

        time.sleep(random.uniform(2, 4))

        linkedin.close()
        return success

    except Exception as e:
        print(f"LinkedIn message error: {e}")
        linkedin.close()
        return False
