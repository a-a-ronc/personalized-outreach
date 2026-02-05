"""
Test script for Leadfeeder API integration.

Usage:
    python test_leadfeeder_api.py

This script tests the new Leadfeeder API integration to ensure it's working correctly.
"""

import sys
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_api_configuration():
    """Test 1: Verify API configuration."""
    print("\n" + "="*60)
    print("TEST 1: API Configuration")
    print("="*60)

    try:
        from config import Config

        if Config.LEADFEEDER_API_KEY:
            print("[OK] API Key configured (redacted)")
            return True
        else:
            print("[FAIL] API Key NOT configured in .env file")
            print("   Add this to your .env file:")
            print("   LEADFEEDER_API_KEY=your-leadfeeder-api-key-here")
            return False
    except Exception as e:
        print(f"[FAIL] Configuration error: {e}")
        return False


def test_api_client():
    """Test 2: Initialize API client."""
    print("\n" + "="*60)
    print("TEST 2: API Client Initialization")
    print("="*60)

    try:
        from leadfeeder_api import LeadfeederAPI

        api = LeadfeederAPI()
        print("[OK] API client initialized successfully")
        print(f"   Base URL: {api.BASE_URL}")
        print(f"   Rate limit: {api.rate_limit} requests per {api.rate_limit_window}s")
        return True
    except ValueError as e:
        print(f"[FAIL] API client initialization failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        return False


def test_get_accounts():
    """Test 3: Fetch Leadfeeder accounts."""
    print("\n" + "="*60)
    print("TEST 3: Fetch Accounts")
    print("="*60)

    try:
        from leadfeeder_api import LeadfeederAPI

        api = LeadfeederAPI()
        accounts = api.get_accounts()

        if accounts:
            print(f"[OK] Found {len(accounts)} account(s)")
            for i, account in enumerate(accounts, 1):
                account_id = account.get("id")
                attrs = account.get("attributes", {})
                name = attrs.get("name", "Unknown")
                timezone = attrs.get("timezone", "Unknown")
                print(f"\n   Account {i}:")
                print(f"   - ID: {account_id}")
                print(f"   - Name: {name}")
                print(f"   - Timezone: {timezone}")
            return accounts
        else:
            print("[FAIL] No accounts found")
            print("   This may indicate:")
            print("   - Invalid API token")
            print("   - Token doesn't have access to any accounts")
            return None
    except Exception as e:
        print(f"[FAIL] Failed to fetch accounts: {e}")
        return None


def test_get_leads(account_id):
    """Test 4: Fetch leads for an account."""
    print("\n" + "="*60)
    print("TEST 4: Fetch Leads (Last 7 Days)")
    print("="*60)

    try:
        from leadfeeder_api import LeadfeederAPI

        api = LeadfeederAPI()

        # Fetch last 7 days
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        print(f"   Date range: {start_date} to {end_date}")
        print(f"   Fetching leads... (this may take a moment)")

        leads = api.get_leads(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            max_pages=2  # Limit to 2 pages for testing
        )

        if leads:
            print(f"[OK] Found {len(leads)} lead(s)")

            # Show first 3 leads as examples
            for i, lead in enumerate(leads[:3], 1):
                lead_id = lead.get("id")
                attrs = lead.get("attributes", {})
                name = attrs.get("name", "Unknown")
                industry = attrs.get("industry", "Unknown")
                visits = attrs.get("visits", 0)
                last_visit = attrs.get("last_visit_date", "Unknown")

                print(f"\n   Lead {i}:")
                print(f"   - ID: {lead_id}")
                print(f"   - Company: {name}")
                print(f"   - Industry: {industry}")
                print(f"   - Visits: {visits}")
                print(f"   - Last Visit: {last_visit}")

            if len(leads) > 3:
                print(f"\n   ... and {len(leads) - 3} more leads")

            return leads
        else:
            print("[WARN]  No leads found in the last 7 days")
            print("   This is normal if you haven't had website visitors recently")
            return []
    except Exception as e:
        print(f"[FAIL] Failed to fetch leads: {e}")
        return None


def test_database_storage(leads):
    """Test 5: Store leads in database."""
    print("\n" + "="*60)
    print("TEST 5: Database Storage")
    print("="*60)

    if not leads:
        print("[WARN]  Skipping (no leads to store)")
        return True

    try:
        from leadfeeder_api import store_leadfeeder_api_data

        print(f"   Storing {len(leads)} leads in database...")
        stored_count = store_leadfeeder_api_data(leads)

        if stored_count > 0:
            print(f"[OK] Successfully stored {stored_count} leads")
            return True
        else:
            print("[WARN]  No leads were stored (may have been duplicates)")
            return True
    except Exception as e:
        print(f"[FAIL] Database storage failed: {e}")
        return False


def test_status_check():
    """Test 6: Check integration status."""
    print("\n" + "="*60)
    print("TEST 6: Integration Status")
    print("="*60)

    try:
        from leadfeeder_api import get_leadfeeder_status

        status = get_leadfeeder_status()

        print(f"   Configured: {status['configured']}")
        print(f"   API Working: {status['api_working']}")
        print(f"   Active Companies: {status['active_companies']}")
        print(f"   Expiring Soon: {status['expiring_soon']}")

        if status['account_info']:
            account_name = status['account_info'].get('attributes', {}).get('name', 'Unknown')
            print(f"   Account: {account_name}")

        if status['status']:
            print(f"   Last Sync: {status['status'].get('last_sync_at', 'Never')}")
            print(f"   Status: {status['status'].get('status', 'Unknown')}")

        print("[OK] Status check complete")
        return True
    except Exception as e:
        print(f"[FAIL] Status check failed: {e}")
        return False


def run_full_test():
    """Run all tests in sequence."""
    print("\n" + "="*70)
    print(" "*15 + "LEADFEEDER API INTEGRATION TEST")
    print("="*70)

    results = {}

    # Test 1: Configuration
    results['config'] = test_api_configuration()
    if not results['config']:
        print("\n[FAIL] Cannot proceed without API configuration")
        return

    # Test 2: API Client
    results['client'] = test_api_client()
    if not results['client']:
        print("\n[FAIL] Cannot proceed without API client")
        return

    # Test 3: Get Accounts
    accounts = test_get_accounts()
    results['accounts'] = accounts is not None

    if not accounts:
        print("\n[FAIL] Cannot proceed without accounts")
        print("\n" + "="*70)
        print_summary(results)
        return

    # Test 4: Get Leads
    account_id = accounts[0].get("id")
    leads = test_get_leads(account_id)
    results['leads'] = leads is not None

    # Test 5: Database Storage
    if leads:
        results['storage'] = test_database_storage(leads)
    else:
        results['storage'] = True  # Skip if no leads

    # Test 6: Status Check
    results['status'] = test_status_check()

    # Print Summary
    print("\n" + "="*70)
    print_summary(results)


def print_summary(results):
    """Print test summary."""
    print("\n" + "="*70)
    print(" "*25 + "TEST SUMMARY")
    print("="*70)

    test_names = {
        'config': 'API Configuration',
        'client': 'API Client Initialization',
        'accounts': 'Account Retrieval',
        'leads': 'Lead Fetching',
        'storage': 'Database Storage',
        'status': 'Status Check'
    }

    passed = 0
    total = 0

    for key, name in test_names.items():
        if key in results:
            total += 1
            if results[key]:
                passed += 1
                print(f"[OK] {name}")
            else:
                print(f"[FAIL] {name}")

    print("="*70)
    print(f"\nRESULT: {passed}/{total} tests passed")

    if passed == total:
        print("\nSUCCESS All tests passed! Your Leadfeeder API integration is working correctly.")
        print("\nNext steps:")
        print("1. The scheduler will automatically sync data daily at 2 AM UTC")
        print("2. You can manually trigger syncs via the dashboard")
        print("3. Check the visitor_companies table to see imported data")
    else:
        print("\n[WARN]  Some tests failed. Please review the errors above.")
        print("\nTroubleshooting:")
        print("1. Verify your API key is correct in .env")
        print("2. Check the LEADFEEDER_API_SETUP.md guide")
        print("3. Review the logs for detailed error messages")

    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        run_full_test()
    except KeyboardInterrupt:
        print("\n\n[WARN]  Test interrupted by user")
    except Exception as e:
        print(f"\n\n[FAIL] Unexpected error during testing: {e}")
        import traceback
        traceback.print_exc()
