import requests
import time
import logging
from typing import Optional, Dict, List
from config import Config

logger = logging.getLogger(__name__)


class ApolloEnricher:
    """Apollo.io API client for lead enrichment"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or Config.APOLLO_API_KEY
        self.base_url = "https://api.apollo.io/api/v1"  # Fixed: added /api prefix
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Cache-Control": "no-cache"
        })

        if not self.api_key:
            logger.warning("Apollo API key not configured. Enrichment features will be unavailable.")

    def enrich_person(self, email: str = None, first_name: str = None,
                     last_name: str = None, company: str = None,
                     domain: str = None, linkedin_url: str = None,
                     person_id: str = None,
                     reveal_personal_emails: bool = False,
                     reveal_phone_number: bool = False,
                     webhook_url: str = None,
                     run_waterfall_email: bool = False,
                     run_waterfall_phone: bool = False) -> Optional[Dict]:
        """
        Enrich a person record with Apollo data

        Args:
            email: Person's email address
            first_name: First name (optional, improves match rate)
            last_name: Last name (optional)
            company: Company name (optional)
            domain: Company domain (optional)
            linkedin_url: LinkedIn URL (optional)
            person_id: Apollo person ID (optional)
            reveal_personal_emails: Whether to reveal personal emails (credits)
            reveal_phone_number: Whether to reveal phone numbers (credits)
            webhook_url: URL to receive phone number webhook (required if reveal_phone_number=True)
            run_waterfall_email: Enable email waterfall enrichment
            run_waterfall_phone: Enable phone waterfall enrichment

        Returns:
            {
                'name': str,
                'title': str,
                'seniority': str,  # C-Level, VP, Director, Manager, etc.
                'departments': list[str],
                'email_status': str,  # verified, unverified, etc.
                'email': str,
                'phone': str,
                'linkedin_url': str,
                'person_id': str,
                'job_start_date': str,
                'company': {
                    'id': str,
                    'name': str,
                    'domain': str,
                    'industry': str,
                    'employee_count': int
                }
            }
        """
        endpoint = f"{self.base_url}/people/match"
        payload = {"api_key": self.api_key}

        if email:
            payload["email"] = email
        if person_id:
            payload["id"] = person_id
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        if company:
            payload["organization_name"] = company
        if domain:
            payload["domain"] = domain
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url
        if reveal_personal_emails:
            payload["reveal_personal_emails"] = True
        if reveal_phone_number:
            payload["reveal_phone_number"] = True
            if webhook_url:
                payload["webhook_url"] = webhook_url
            else:
                logger.warning("reveal_phone_number=True requires webhook_url to receive results")
        if run_waterfall_email:
            payload["run_waterfall_email"] = True
        if run_waterfall_phone:
            payload["run_waterfall_phone"] = True

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("person"):
                person = data["person"]
                org = person.get("organization") or {}

                # Handle waterfall status if present
                waterfall_info = data.get("waterfall", {})
                if waterfall_info:
                    logger.info(f"Waterfall enrichment: {waterfall_info.get('status')} - {waterfall_info.get('message')}")

                return {
                    "name": person.get("name", ""),
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "title": person.get("title", ""),
                    "seniority": person.get("seniority", ""),
                    "departments": person.get("departments", []),
                    "email_status": person.get("email_status", ""),
                    "email": person.get("email", ""),
                    "personal_emails": person.get("personal_emails", []),
                    "phone": person.get("phone_numbers", [{}])[0].get("raw_number", "") if person.get("phone_numbers") else "",
                    "phone_numbers": person.get("phone_numbers", []),
                    "linkedin_url": person.get("linkedin_url", ""),
                    "person_id": person.get("id", ""),
                    "job_start_date": person.get("job_start_date", ""),
                    "employment_history": person.get("employment_history", []),
                    "company": {
                        "id": org.get("id", ""),
                        "name": org.get("name", ""),
                        "domain": org.get("primary_domain", ""),
                        "industry": org.get("industry", ""),
                        "employee_count": org.get("estimated_num_employees", 0)
                    },
                    "waterfall_status": waterfall_info
                }
            else:
                logger.warning(f"No person match found for {email or first_name} {last_name}")
                return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Apollo API authentication failed. Check your API key.")
            elif e.response.status_code == 429:
                logger.error("Apollo API rate limit exceeded. Please slow down requests.")
            elif e.response.status_code == 402:
                logger.error("Apollo API credits exhausted. Please purchase more credits.")
            else:
                logger.error(f"Apollo API HTTP error for {email}: {e.response.status_code} - {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Apollo API request error for {email}: {e}")
            return None
        finally:
            time.sleep(Config.APOLLO_RATE_LIMIT_DELAY)

    def bulk_enrich_people(self, people: List[Dict],
                           reveal_personal_emails: bool = False,
                           reveal_phone_number: bool = False,
                           webhook_url: str = None,
                           run_waterfall_email: bool = False,
                           run_waterfall_phone: bool = False) -> List[Dict]:
        """
        Bulk enrich people (up to 10 per call).

        Each entry in people should include keys like:
        {
            "email": "",
            "first_name": "",
            "last_name": "",
            "organization_name": "",
            "domain": "",
            "linkedin_url": "",
            "person_id": ""
        }
        """
        if not people:
            return []

        endpoint = f"{self.base_url}/people/bulk_match"
        payload = {
            "api_key": self.api_key,
            "reveal_personal_emails": reveal_personal_emails,
            "reveal_phone_number": reveal_phone_number,
            "details": [
                {
                    "email": item.get("email"),
                    "first_name": item.get("first_name"),
                    "last_name": item.get("last_name"),
                    "organization_name": item.get("organization_name"),
                    "domain": item.get("domain"),
                    "linkedin_url": item.get("linkedin_url"),
                    "id": item.get("person_id")
                }
                for item in people
            ]
        }

        if webhook_url:
            payload["webhook_url"] = webhook_url
        if run_waterfall_email:
            payload["run_waterfall_email"] = True
        if run_waterfall_phone:
            payload["run_waterfall_phone"] = True

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("people", []) or data.get("persons", []) or []
        except requests.exceptions.RequestException as e:
            logger.error(f"Apollo bulk API error: {e}")
            return []
        finally:
            time.sleep(Config.APOLLO_RATE_LIMIT_DELAY)

    def search_people(self, search_payload: Dict) -> List[Dict]:
        """
        Search for people without consuming credits.
        Uses /mixed_people/api_search.
        """
        endpoint = f"{self.base_url}/mixed_people/api_search"
        payload = {"api_key": self.api_key}
        payload.update(search_payload or {})

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("people", []) or data.get("contacts", []) or []
        except requests.exceptions.RequestException as e:
            logger.error(f"Apollo search API error: {e}")
            return []
        finally:
            time.sleep(Config.APOLLO_RATE_LIMIT_DELAY)

    def enrich_company(self, company_name: str = None, domain: str = None) -> Optional[Dict]:
        """
        Enrich company data

        Args:
            company_name: Company name
            domain: Company domain (more reliable for matching)

        Returns:
            {
                'name': str,
                'domain': str,
                'industry': str,
                'employee_count': int,
                'estimated_revenue': str,
                'founded_year': int,
                'technologies': list[str],
                'seo_description': str,
                'current_job_openings_count': int,
                'company_id': str
            }
        """
        endpoint = f"{self.base_url}/organizations/enrich"
        payload = {
            "api_key": self.api_key
        }

        if domain:
            payload["domain"] = domain
        elif company_name:
            payload["organization_name"] = company_name
        else:
            logger.error("Either company_name or domain must be provided")
            return None

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("organization"):
                org = data["organization"]
                return {
                    "name": org.get("name", ""),
                    "domain": org.get("primary_domain", ""),
                    "industry": org.get("industry", ""),
                    "employee_count": org.get("estimated_num_employees", 0),
                    "estimated_revenue": org.get("estimated_annual_revenue", ""),
                    "founded_year": org.get("founded_year"),
                    "technologies": [tech.get("name") for tech in org.get("technologies", [])],
                    "seo_description": org.get("seo_description", ""),
                    "current_job_openings_count": org.get("current_job_openings_count", 0),
                    "company_id": org.get("id", "")
                }
            else:
                logger.warning(f"No company match found for {company_name or domain}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Apollo API error for {company_name or domain}: {e}")
            return None
        finally:
            time.sleep(Config.APOLLO_RATE_LIMIT_DELAY)

    def get_account_info(self) -> Optional[Dict]:
        """
        Get Apollo account information including credits remaining.

        Returns:
            {
                'email': str,
                'team_id': str,
                'credits': {
                    'email_credits': int,
                    'export_credits': int,
                    'mobile_credits': int
                },
                'account_status': str
            }
        """
        endpoint = f"{self.base_url}/auth/health"
        payload = {"api_key": self.api_key}

        try:
            response = self.session.get(endpoint, params=payload)
            response.raise_for_status()
            data = response.json()

            return {
                "email": data.get("email", ""),
                "team_id": data.get("team_id", ""),
                "credits": {
                    "email_credits": data.get("email_credits_remaining", 0),
                    "export_credits": data.get("export_credits_remaining", 0),
                    "mobile_credits": data.get("mobile_credits_remaining", 0)
                },
                "is_active": data.get("is_active", False),
                "account_status": "active" if data.get("is_active") else "inactive"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Apollo account info API error: {e}")
            return None
        finally:
            time.sleep(Config.APOLLO_RATE_LIMIT_DELAY)

    def get_company_job_postings(self, company_id: str) -> List[Dict]:
        """
        Get current job postings for a company (intent signal)

        Returns:
            [
                {
                    'title': str,
                    'department': str,
                    'posted_at': str
                }
            ]
        """
        endpoint = f"{self.base_url}/organizations/{company_id}/job_postings"
        payload = {"api_key": self.api_key}

        try:
            response = self.session.get(endpoint, params=payload)
            response.raise_for_status()
            data = response.json()

            return [
                {
                    "title": job.get("title", ""),
                    "department": job.get("department", ""),
                    "posted_at": job.get("posted_at", "")
                }
                for job in data.get("job_postings", [])
            ]
        except requests.exceptions.RequestException as e:
            logger.error(f"Apollo API error for company {company_id} job postings: {e}")
            return []
        finally:
            time.sleep(Config.APOLLO_RATE_LIMIT_DELAY)


def get_webhook_url(base_url: str = None) -> str:
    """
    Generate the webhook URL for Apollo phone reveals.

    Args:
        base_url: Your application's base URL (e.g., https://your-app.railway.app)

    Returns:
        Full webhook URL for Apollo
    """
    from config import Config
    base = base_url or Config.BASE_URL
    return f"{base}/api/webhooks/apollo/phone-reveal"


def detect_wms_system(technologies: List[str]) -> str:
    """Detect WMS system from technology stack"""
    wms_mapping = {
        'Manhattan Associates': 'manhattan',
        'Manhattan WMS': 'manhattan',
        'Blue Yonder': 'blue_yonder',
        'JDA Software': 'blue_yonder',
        'SAP': 'sap',
        'Oracle': 'oracle',
        'Infor': 'infor',
        'NetSuite': 'netsuite',
        'HighJump': 'highjump'
    }

    for tech in technologies:
        for wms_name, wms_key in wms_mapping.items():
            if wms_name.lower() in tech.lower():
                return wms_key
    return 'unknown'


def detect_equipment_signals(technologies: List[str], description: str = "") -> List[str]:
    """Detect equipment/automation signals from technologies and description"""
    signals = []
    combined_text = f"{' '.join(technologies)} {description}".lower()

    equipment_keywords = {
        'sortation': ['sortation', 'sorter', 'cross-belt', 'tilt-tray', 'shoe sorter'],
        'conveyor': ['conveyor', 'conveying'],
        'asrs': ['asrs', 'automated storage', 'miniload', 'autostore', 'attabotics'],
        'agv_amr': ['agv', 'amr', 'autonomous mobile robot', 'locus', 'fetch', 'geek+'],
        'shuttle': ['pallet shuttle', 'shuttle system'],
        'vlm': ['vertical lift module', 'vlm', 'kardex'],
        'wms': ['wms', 'warehouse management'],
        'automation': ['automation', 'automated']
    }

    for signal_type, keywords in equipment_keywords.items():
        if any(keyword in combined_text for keyword in keywords):
            signals.append(signal_type)

    return signals


def calculate_intent_score(person_data: Dict, company_data: Dict, job_postings: List[Dict]) -> float:
    """
    Calculate buying intent score based on enrichment signals

    Scoring factors:
    - Job postings for warehouse/automation roles (+0.15 each, max +0.3)
    - Seniority (decision maker) (+0.2)
    - Revenue signals budget (+0.2)
    - Technology sophistication (+0.15)
    - Job opening count (growth signal) (+0.15)

    Returns:
        Float between 0.0 and 1.0
    """
    score = 0.0

    # Job postings (warehouse, automation, supply chain roles = high intent)
    warehouse_keywords = ['warehouse', 'distribution', 'supply chain', 'logistics',
                          'operations', 'automation', 'controls', 'engineering']
    relevant_jobs = [
        job for job in job_postings
        if any(kw in job.get('title', '').lower() for kw in warehouse_keywords)
    ]
    score += min(len(relevant_jobs) * 0.15, 0.3)

    # Seniority (decision makers)
    seniority = person_data.get('seniority', '').lower()
    if any(level in seniority for level in ['c-level', 'vp', 'vice president', 'director']):
        score += 0.2

    # Revenue (signals budget)
    revenue = company_data.get('estimated_revenue', '')
    if any(rev in revenue for rev in ['$50M', '$100M', '$200M', '$500M']):
        score += 0.2

    # Technology sophistication
    tech_count = len(company_data.get('technologies', []))
    if tech_count > 10:
        score += 0.15
    elif tech_count > 5:
        score += 0.1

    # Job opening count (growth signal)
    job_count = company_data.get('current_job_openings_count', 0)
    if job_count > 10:
        score += 0.15
    elif job_count > 5:
        score += 0.1

    return min(score, 1.0)
