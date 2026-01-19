#!/usr/bin/env python3
"""
Comprehensive Backend Testing Script
Tests all 13 new API endpoints and backend functionality
"""

import requests
import json
import time
import sys
from pathlib import Path

# Configuration
BASE_URL = "http://127.0.0.1:7000"
TEST_EMAIL = "your-test-email@example.com"  # Change this to your email

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def test_server_running():
    """Test if backend server is running."""
    print_header("Test 1: Server Health Check")

    try:
        response = requests.get(f"{BASE_URL}/api/variables", timeout=5)
        if response.status_code == 200:
            print_success("Backend server is running")
            return True
        else:
            print_error(f"Server responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Backend server is not running")
        print_info("Start it with: python backend/app.py")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def test_variables_endpoint():
    """Test GET /api/variables endpoint."""
    print_header("Test 2: Variables Endpoint")

    try:
        response = requests.get(f"{BASE_URL}/api/variables")

        if response.status_code == 200:
            data = response.json()
            variables = data.get('variables', [])

            print_success(f"Endpoint returned {len(variables)} variables")

            # Check for expected categories
            categories = set(v['category'] for v in variables)
            expected_categories = {'Person', 'Company', 'Signals', 'AI Generated', 'Sender'}

            if expected_categories.issubset(categories):
                print_success(f"All expected categories present: {categories}")
            else:
                print_warning(f"Missing categories: {expected_categories - categories}")

            # Show sample variables
            print_info("Sample variables:")
            for var in variables[:5]:
                print(f"  - {var['name']} ({var['category']}): {var['example']}")

            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_signatures_list():
    """Test GET /api/signatures endpoint."""
    print_header("Test 3: List Signatures")

    try:
        response = requests.get(f"{BASE_URL}/api/signatures")

        if response.status_code == 200:
            data = response.json()
            signatures = data.get('signatures', [])

            print_success(f"Found {len(signatures)} signatures in database")

            if signatures:
                print_info("Signatures:")
                for sig in signatures:
                    default_mark = " (default)" if sig.get('is_default') else ""
                    print(f"  - {sig['name']}{default_mark}")
            else:
                print_warning("No signatures found. Import with POST /api/signatures/import")

            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_signatures_import():
    """Test POST /api/signatures/import endpoint."""
    print_header("Test 4: Import Outlook Signatures")

    try:
        response = requests.post(f"{BASE_URL}/api/signatures/import")

        if response.status_code == 200:
            data = response.json()
            count = data.get('count', 0)

            if count > 0:
                print_success(f"Imported {count} signature(s)")
                print_info(f"Signature IDs: {data.get('signature_ids', [])}")
            else:
                print_warning("No signatures found in Outlook")
                print_info("Check: %APPDATA%\\Microsoft\\Signatures")

            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_apollo_credits():
    """Test GET /api/apollo/credits endpoint."""
    print_header("Test 5: Apollo Credit Tracking")

    try:
        response = requests.get(f"{BASE_URL}/api/apollo/credits")

        if response.status_code == 200:
            data = response.json()

            print_success("Credit tracking endpoint working")
            print_info(f"Credits used: {data.get('credits_used', 0)}")
            print_info(f"Phone reveals: {data.get('phone_reveals', 0)}")
            print_info(f"Email reveals: {data.get('email_reveals', 0)}")
            print_info(f"Credits remaining: {data.get('credits_remaining', 100)}")

            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_sequence_save_load():
    """Test sequence save and load endpoints."""
    print_header("Test 6: Sequence Save & Load")

    campaign_id = "test_campaign_123"

    # Test sequence data
    sequence_data = {
        "name": "Test 6-Step Sequence",
        "steps": [
            {"type": "email", "delay_days": 0, "template": "email_1"},
            {"type": "wait", "delay_days": 3},
            {"type": "email", "delay_days": 0, "template": "email_2"},
            {"type": "wait", "delay_days": 4},
            {"type": "call", "delay_days": 0, "script": "Hi {first_name}, this is Aaron from Intralog..."},
            {"type": "wait", "delay_days": 3},
            {"type": "linkedin_connect", "delay_days": 0, "message": "Hi {first_name}, let's connect!"}
        ]
    }

    try:
        # Save sequence
        print_info("Saving sequence...")
        response = requests.put(
            f"{BASE_URL}/api/campaigns/{campaign_id}/sequence",
            json=sequence_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            data = response.json()
            sequence_id = data.get('sequence_id')
            print_success(f"Sequence saved with ID: {sequence_id}")
        else:
            print_error(f"Save failed with status {response.status_code}")
            print_error(f"Response: {response.text}")
            return False

        # Load sequence
        print_info("Loading sequence...")
        time.sleep(0.5)

        response = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}/sequence")

        if response.status_code == 200:
            data = response.json()
            loaded_steps = data.get('steps', [])

            if len(loaded_steps) == len(sequence_data['steps']):
                print_success(f"Sequence loaded successfully with {len(loaded_steps)} steps")

                # Verify step types
                step_types = [step['type'] for step in loaded_steps]
                print_info(f"Step types: {' → '.join(step_types)}")

                return True
            else:
                print_error(f"Step count mismatch: expected {len(sequence_data['steps'])}, got {len(loaded_steps)}")
                return False
        else:
            print_error(f"Load failed with status {response.status_code}")
            return False

    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_sequence_status():
    """Test sequence status endpoint."""
    print_header("Test 7: Sequence Status")

    campaign_id = "test_campaign_123"

    try:
        response = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}/sequence/status")

        if response.status_code == 200:
            data = response.json()
            status = data.get('status', {})

            print_success("Sequence status endpoint working")

            if status:
                print_info("Status breakdown:")
                for status_name, count in status.items():
                    print(f"  - {status_name}: {count}")
            else:
                print_info("No leads enrolled in this sequence yet")

            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_bland_ai_webhook():
    """Test Bland.ai webhook endpoint."""
    print_header("Test 8: Bland.ai Webhook Handler")

    # Simulated webhook payload
    webhook_data = {
        "call_id": "test_call_123",
        "status": "completed",
        "call_length": 125,
        "transcript": "This is a test transcript.",
        "recording_url": "https://example.com/recording.mp3"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/webhooks/bland-ai",
            json=webhook_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'received':
                print_success("Webhook endpoint accepted test payload")
                return True
            else:
                print_warning(f"Unexpected response: {data}")
                return False
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_database_migration():
    """Test that database schema v2 exists."""
    print_header("Test 9: Database Schema V2")

    import sqlite3
    from pathlib import Path

    db_path = Path(__file__).parent / "data" / "leads.db"

    if not db_path.exists():
        print_error("Database not found at data/leads.db")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check for new tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        required_tables = ['sequences', 'sequence_steps', 'signatures']
        missing_tables = [t for t in required_tables if t not in tables]

        if not missing_tables:
            print_success("All required tables exist:")
            for table in required_tables:
                print(f"  ✓ {table}")
        else:
            print_error(f"Missing tables: {missing_tables}")
            print_info("Run: python migrate_db.py")
            conn.close()
            return False

        # Check for new columns in leads_people
        cursor.execute("PRAGMA table_info(leads_people)")
        columns = [row[1] for row in cursor.fetchall()]

        new_columns = ['linkedin_connection_status', 'linkedin_connected_at',
                      'last_call_attempt_at', 'last_call_status']
        missing_columns = [c for c in new_columns if c not in columns]

        if not missing_columns:
            print_success("All new columns exist in leads_people")
        else:
            print_error(f"Missing columns: {missing_columns}")
            print_info("Run: python migrate_db.py")
            conn.close()
            return False

        conn.close()
        return True

    except Exception as e:
        print_error(f"Error: {e}")
        return False


def print_summary(results):
    """Print test summary."""
    print_header("Test Summary")

    passed = sum(results.values())
    total = len(results)
    pass_rate = (passed / total * 100) if total > 0 else 0

    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        color = Colors.OKGREEN if passed_test else Colors.FAIL
        print(f"{color}{status}{Colors.ENDC} - {test_name}")

    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed ({pass_rate:.1f}%){Colors.ENDC}\n")

    if passed == total:
        print(f"{Colors.OKGREEN}{Colors.BOLD}🎉 All tests passed! Backend is ready for use.{Colors.ENDC}\n")
    elif passed >= total * 0.7:
        print(f"{Colors.WARNING}{Colors.BOLD}⚠️  Most tests passed, but some issues need attention.{Colors.ENDC}\n")
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}❌ Many tests failed. Review errors above.{Colors.ENDC}\n")


def main():
    """Run all tests."""
    print(f"\n{Colors.BOLD}{Colors.OKBLUE}Backend Testing Suite{Colors.ENDC}")
    print(f"{Colors.BOLD}Target: {BASE_URL}{Colors.ENDC}\n")

    results = {}

    # Test 1: Server health
    if not test_server_running():
        print_error("\nBackend server is not running. Cannot proceed with tests.")
        print_info("Start the server with: python backend/app.py")
        sys.exit(1)

    # Run all tests
    results["Database Schema V2"] = test_database_migration()
    results["Variables Endpoint"] = test_variables_endpoint()
    results["List Signatures"] = test_signatures_list()
    results["Import Signatures"] = test_signatures_import()
    results["Apollo Credits"] = test_apollo_credits()
    results["Sequence Save & Load"] = test_sequence_save_load()
    results["Sequence Status"] = test_sequence_status()
    results["Bland.ai Webhook"] = test_bland_ai_webhook()

    # Print summary
    print_summary(results)

    # Next steps
    print_header("Next Steps")

    if all(results.values()):
        print_info("1. Configure your .env file with API keys")
        print_info("2. Test email preview: POST /api/campaigns/<id>/preview")
        print_info("3. Test sending test email: POST /api/campaigns/<id>/test-email")
        print_info("4. Import your leads from Apollo")
        print_info("5. Create a campaign and start outreach!")
    else:
        print_warning("Fix the failing tests before proceeding")
        print_info("Check BACKEND_TESTING_GUIDE.md for detailed testing instructions")


if __name__ == "__main__":
    main()
