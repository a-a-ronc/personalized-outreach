from __future__ import annotations

import json
import os
import socket
import sys
import uuid
import logging
import hashlib
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, abort, jsonify, request
from openai import OpenAI
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = BASE_DIR / "data" / "campaigns.json"
EVENTS_FILE = BASE_DIR / "data" / "events.json"
REPLIES_FILE = BASE_DIR / "data" / "replies.json"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from config import Config  # noqa: E402
from main import generate_campaigns  # noqa: E402
from lead_registry import (  # noqa: E402
    init_db,
    upgrade_schema_v2,
    upgrade_schema_v3,
    upgrade_schema_v4,
    upgrade_schema_v5,
    upgrade_schema_v6,
    upgrade_schema_v7,
    upsert_company,
    upsert_person,
    get_person_by_key,
    get_person_by_email,
    get_company_by_key,
    is_suppressed,
    enqueue_enrichment,
    insert_queue_record,
    update_queue_status,
    get_queue_items,
    get_queue_summary,
    get_people_for_campaign,
    calculate_enrichment_hash,
    recent_request_hash,
    log_outreach,
    utc_now
)
from lead_scoring import (  # noqa: E402
    extract_features,
    score_icp,
    compute_automation_readiness,
    assign_strategy,
    normalize_text as normalize_scoring_text
)
from auth import (  # noqa: E402
    init_auth_tables,
    create_default_admin,
    create_user,
    authenticate_user,
    require_auth,
    require_admin,
    get_all_users,
    update_user,
    change_password,
    get_current_user_from_token
)

# Configure Flask to serve React frontend
DASHBOARD_DIST = BASE_DIR / "dashboard" / "dist"
app = Flask(__name__,
            static_folder=str(DASHBOARD_DIST),
            static_url_path='')
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# Initialize WebSocket support for VNC viewing
from flask_sock import Sock
sock = Sock(app)

# Initialize database and run all migrations
init_db()
upgrade_schema_v2()
upgrade_schema_v3()
upgrade_schema_v4()
upgrade_schema_v5()
upgrade_schema_v6()
upgrade_schema_v7()

# Initialize authentication
init_auth_tables()
create_default_admin()

ALLOWED_EXTENSIONS = {".csv"}
REPLY_CLASSES = [
    "Positive interest",
    "Soft interest",
    "Neutral / info",
    "Objection",
    "Referral",
    "Unsubscribe",
    "Out of office",
    "Spam / hostile"
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ====================
# HELPER FUNCTIONS: Email Utilities
# ====================

def html_to_plain_text(html):
    """Convert HTML email to plain text."""
    from bs4 import BeautifulSoup

    # Remove scripts and styles
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup(["script", "style"]):
        script.extract()

    # Get text
    text = soup.get_text()

    # Break into lines and remove leading/trailing space
    lines = (line.strip() for line in text.splitlines())

    # Break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))

    # Drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text


def send_via_sendgrid(to_email, from_email, from_name, subject, html_body, plain_body=None):
    """Send email via SendGrid API."""
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content

    try:
        sg = SendGridAPIClient(api_key=Config.SENDGRID_API_KEY)

        # Build email
        mail = Mail(
            from_email=Email(from_email, from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_body)
        )

        # Add plain text version if provided
        if plain_body:
            mail.add_content(Content("text/plain", plain_body))

        # Send email
        response = sg.client.mail.send.post(request_body=mail.get())

        return response.status_code == 202
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False


def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response


app.after_request(add_cors_headers)


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return app.make_default_options_response()


@app.errorhandler(Exception)
def handle_exception(error):
    logger.exception("Unhandled error")
    return jsonify({"error": str(error)}), 500


def read_json_file(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("Failed to read %s", path)
        return fallback
    if not content.strip():
        return fallback
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in %s", path)
        return fallback
    return data if isinstance(data, dict) else fallback


def load_json() -> dict:
    data = read_json_file(DATA_FILE, {"campaigns": []})
    if not isinstance(data.get("campaigns"), list):
        return {"campaigns": []}
    return data


def save_json(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_events() -> list[dict]:
    data = read_json_file(EVENTS_FILE, {"events": []})
    events = data.get("events", [])
    return events if isinstance(events, list) else []


def save_events(events: list[dict]) -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_FILE.write_text(json.dumps({"events": events}, indent=2), encoding="utf-8")


def load_replies() -> list[dict]:
    data = read_json_file(REPLIES_FILE, {"replies": []})
    replies = data.get("replies", [])
    return replies if isinstance(replies, list) else []


def save_replies(replies: list[dict]) -> None:
    REPLIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPLIES_FILE.write_text(json.dumps({"replies": replies}, indent=2), encoding="utf-8")


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def relative_path(path: Path) -> str:
    return path.relative_to(BASE_DIR).as_posix()


def safe_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return value


def normalize_locations(locations) -> list[str]:
    if not locations:
        return []
    if isinstance(locations, list):
        output = []
        for item in locations:
            if isinstance(item, dict):
                city = normalize_scoring_text(item.get("city", ""))
                state = normalize_scoring_text(item.get("state", ""))
                if city and state:
                    output.append(f"{city}, {state}")
                elif city or state:
                    output.append(city or state)
            else:
                output.append(str(item))
        return [loc for loc in output if loc]
    return [str(locations)]


def parse_apollo_search_person(person: dict) -> tuple[dict, dict]:
    org = person.get("organization") or person.get("company") or {}
    org_id = org.get("id") or person.get("organization_id") or person.get("org_id") or ""
    org_domain = org.get("primary_domain") or org.get("domain") or person.get("organization_domain") or ""
    org_name = org.get("name") or person.get("organization_name") or ""

    company_record = {
        "apollo_org_id": org_id,
        "company_id": org_id,
        "name": org_name,
        "domain": org_domain,
        "industry": org.get("industry", "") or person.get("industry", ""),
        "employee_count": org.get("estimated_num_employees", 0) or org.get("employee_count", 0),
        "estimated_revenue": org.get("estimated_annual_revenue", ""),
        "technologies": [tech.get("name") for tech in org.get("technologies", [])] if org.get("technologies") else [],
        "wms_system": "",
        "equipment_signals": [],
        "job_postings_count": org.get("current_job_openings_count", 0) or 0,
        "job_postings_relevant": 0,
        "locations": normalize_locations(org.get("locations", [])),
        "controls_roles_hiring": False
    }

    departments = person.get("departments") or []
    department = departments[0] if isinstance(departments, list) and departments else person.get("department", "")
    person_record = {
        "apollo_person_id": person.get("id") or person.get("person_id") or "",
        "first_name": person.get("first_name", ""),
        "last_name": person.get("last_name", ""),
        "title": person.get("title", ""),
        "seniority": person.get("seniority", ""),
        "department": department,
        "email": person.get("email", ""),
        "email_status": person.get("email_status", ""),
        "phone": "",
        "linkedin_url": person.get("linkedin_url", ""),
        "job_start_date": person.get("job_start_date", ""),
        "company_domain": org_domain
    }

    return person_record, company_record


def parse_apollo_person_response(person: dict) -> tuple[dict, dict]:
    org = person.get("organization") or {}
    company_record = {
        "apollo_org_id": org.get("id", ""),
        "company_id": org.get("id", ""),
        "name": org.get("name", ""),
        "domain": org.get("primary_domain", ""),
        "industry": org.get("industry", ""),
        "employee_count": org.get("estimated_num_employees", 0),
        "estimated_revenue": org.get("estimated_annual_revenue", ""),
        "technologies": [tech.get("name") for tech in org.get("technologies", [])] if org.get("technologies") else [],
        "wms_system": "",
        "equipment_signals": [],
        "job_postings_count": org.get("current_job_openings_count", 0) or 0,
        "job_postings_relevant": 0,
        "locations": normalize_locations(org.get("locations", []))
    }

    departments = person.get("departments") or []
    department = departments[0] if isinstance(departments, list) and departments else person.get("department", "")
    person_record = {
        "apollo_person_id": person.get("id", ""),
        "first_name": person.get("first_name", ""),
        "last_name": person.get("last_name", ""),
        "title": person.get("title", ""),
        "seniority": person.get("seniority", ""),
        "department": department,
        "email": person.get("email", ""),
        "email_status": person.get("email_status", ""),
        "phone": person.get("phone_numbers", [{}])[0].get("raw_number", "") if person.get("phone_numbers") else "",
        "linkedin_url": person.get("linkedin_url", ""),
        "job_start_date": person.get("job_start_date", ""),
        "company_domain": org.get("primary_domain", "")
    }

    return person_record, company_record


def person_enrichment_needed(person_row: dict) -> bool:
    if not person_row:
        return True
    email_norm = person_row.get("email_norm") or ""
    email_status = normalize_scoring_text(person_row.get("email_status", ""))
    if email_norm and email_status == "verified":
        return False
    enriched_at = parse_timestamp(person_row.get("enriched_at", ""))
    if enriched_at:
        cutoff = datetime.now(timezone.utc) - timedelta(days=Config.APOLLO_PERSON_TTL_DAYS)
        if enriched_at >= cutoff and email_norm:
            return False
    return True


def company_enrichment_needed(company_row: dict) -> bool:
    if not company_row:
        return True
    enriched_at = parse_timestamp(company_row.get("enriched_at", ""))
    if not enriched_at:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=Config.APOLLO_COMPANY_TTL_DAYS)
    return enriched_at < cutoff


def build_credit_estimate(payload: dict) -> dict:
    def read_float(key, default=0.0):
        try:
            return float(payload.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    l = read_float("L")
    a = read_float("A")
    e = read_float("E")
    p = read_float("P")
    r = read_float("R")
    d = read_float("D")
    ce = read_float("Ce")
    cp = read_float("Cp")
    cr = read_float("Cr")

    n = l * a * (1 - d)
    email_credits = n * e * ce
    mobile_credits = n * p * cp
    enrichment_credits = n * r * cr
    total = n * (e * ce + p * cp + r * cr)

    return {
        "inputs": {"L": l, "A": a, "E": e, "P": p, "R": r, "D": d, "Ce": ce, "Cp": cp, "Cr": cr},
        "net_new": n,
        "email_credits": email_credits,
        "mobile_credits": mobile_credits,
        "enrichment_credits": enrichment_credits,
        "total": total
    }


def get_request_json() -> dict:
    try:
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(timestamp: str) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=Config.OPENAI_API_KEY)


def classify_reply_text(reply_text: str) -> dict:
    prompt = (
        "Classify this outbound sales reply into one class and score sentiment and intent. "
        "Return JSON with keys: reply_class, sentiment_score, intent_score. "
        f"Allowed reply_class values: {', '.join(REPLY_CLASSES)}. "
        "sentiment_score and intent_score must be between 0 and 1. "
        "Reply text:\n"
        f"{reply_text}"
    )

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=120,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
    except Exception:
        data = {}

    reply_class = data.get("reply_class")
    if reply_class not in REPLY_CLASSES:
        reply_class = "Neutral / info"

    sentiment_score = float(data.get("sentiment_score", 0.5))
    intent_score = float(data.get("intent_score", 0.5))
    sentiment_score = max(0.0, min(1.0, sentiment_score))
    intent_score = max(0.0, min(1.0, intent_score))

    return {
        "reply_class": reply_class,
        "sentiment_score": sentiment_score,
        "intent_score": intent_score
    }


def append_event(event: dict) -> dict:
    events = load_events()
    event["event_id"] = event.get("event_id") or str(uuid.uuid4())
    event["timestamp"] = event.get("timestamp") or utc_now()
    events.append(event)
    save_events(events)
    if event.get("event_type") == "email_sent":
        recipient_email = event.get("recipient_email", "")
        person = get_person_by_email(recipient_email)
        if person:
            log_outreach(
                person.get("person_key", ""),
                event.get("campaign_id", ""),
                int(event.get("email_sequence") or 1),
                "sent"
            )
    return event


def lookup_output_row(campaign: dict, recipient_email: str, email_sequence: int | None) -> dict | None:
    output_file = campaign.get("output_file")
    if not output_file:
        return None
    output_path = BASE_DIR / output_file
    if not output_path.exists():
        return None

    try:
        df = pd.read_csv(output_path)
    except Exception:
        return None

    if "recipient_email" not in df.columns:
        return None

    match = df[df["recipient_email"] == recipient_email]
    if email_sequence is not None and "email_sequence" in df.columns:
        match = match[match["email_sequence"] == email_sequence]

    if match.empty:
        return None

    return match.iloc[0].to_dict()


def enrich_event(event: dict, campaign: dict) -> dict:
    recipient_email = event.get("recipient_email")
    email_sequence = event.get("email_sequence")
    if recipient_email:
        row = lookup_output_row(campaign, recipient_email, email_sequence)
    else:
        row = None

    if row:
        event.setdefault("sender_email", row.get("sender_email", ""))
        event.setdefault("icp_segment", row.get("icp_match", ""))
        event.setdefault("pain_theme", row.get("pain_theme", ""))
        event.setdefault("cta_variant_id", row.get("cta_variant_id", ""))
        event.setdefault("subject_variant_id", row.get("subject_variant_id", ""))
        event.setdefault("personalization_hash", row.get("personalization_hash", ""))

    return event


def deterministic_hit(seed: str, rate: float) -> bool:
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return value < rate


def deterministic_choice(seed: str, options: list[str]) -> str:
    if not options:
        return ""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def build_event_base(row: dict, campaign_id: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "email_sequence": int(row.get("email_sequence", 1)) if pd.notna(row.get("email_sequence", 1)) else 1,
        "sender_email": safe_value(row.get("sender_email", "")),
        "recipient_email": safe_value(row.get("recipient_email", "")),
        "icp_segment": safe_value(row.get("icp_match", "")),
        "pain_theme": safe_value(row.get("pain_theme", "")),
        "cta_variant_id": safe_value(row.get("cta_variant_id", "")),
        "subject_variant_id": safe_value(row.get("subject_variant_id", "")),
        "personalization_hash": safe_value(row.get("personalization_hash", ""))
    }


def load_email_template(template_name: str) -> dict:
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        return {"subject": "", "body": ""}

    content = template_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    subject = ""
    body_lines = []

    for idx, line in enumerate(lines):
        if line.startswith("Subject:"):
            subject = line.replace("Subject:", "").strip()
            body_lines = lines[idx + 2 :]
            break

    return {"subject": subject, "body": "\n".join(body_lines).strip()}


def build_default_campaign() -> dict:
    email_1 = load_email_template("email_1.txt")
    email_2 = load_email_template("email_2.txt")
    output_file = "output/campaigns_batch_25.csv"
    if not (BASE_DIR / output_file).exists():
        output_file = ""

    scheduled_count = 0
    if output_file:
        try:
            scheduled_count = len(pd.read_csv(BASE_DIR / output_file))
        except Exception:
            scheduled_count = 0

    return {
        "id": "equipment-first",
        "name": "Equipment First",
        "status": "active",
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "lead_source": "data/Master_Leads_Populated_ICP_Equipment.csv",
        "output_file": output_file,
        "sequence": {
            "email_1": {
                "variant_a": email_1,
                "variant_b": {"subject": email_1["subject"], "body": email_1["body"]}
            },
            "email_2": {
                "variant_a": email_2,
                "variant_b": {"subject": email_2["subject"], "body": email_2["body"]}
            }
        },
        "stats": {
            "scheduled": scheduled_count,
            "sent": 0,
            "delivered": 0,
            "opened": 0,
            "replied": 0,
            "successful": 0,
            "bounced": 0,
            "unsubscribed": 0
        },
        "settings": {
            "sender_emails": [profile["email"] for profile in Config.SENDER_PROFILES],
            "tracking": {"opens": True, "clicks": False},
            "schedule": {
                "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                "start_time": "09:00",
                "end_time": "17:00",
                "timezone": "MST (Mountain Standard Time)"
            },
            "daily_limit": Config.MAX_EMAILS_PER_DAY,
            "follow_up_delay_days": 4,
            "on_hold": False
        }
    }


def ensure_seed_data() -> None:
    data = load_json()
    if data.get("campaigns"):
        for campaign in data["campaigns"]:
            normalize_campaign_settings(campaign)
            normalize_campaign_stats(campaign)
        save_json(data)
        return
    data["campaigns"] = [build_default_campaign()]
    save_json(data)


def find_campaign(data: dict, campaign_id: str) -> dict | None:
    for campaign in data.get("campaigns", []):
        if campaign.get("id") == campaign_id:
            return campaign
    return None


def normalize_campaign_settings(campaign: dict) -> None:
    settings = campaign.get("settings") or {}
    schedule = settings.get("schedule") or {}

    if "sender_emails" not in settings:
        settings["sender_emails"] = [profile["email"] for profile in Config.SENDER_PROFILES]
    if "tracking" not in settings:
        settings["tracking"] = {"opens": True, "clicks": False}

    schedule.setdefault("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
    schedule.setdefault("start_time", "09:00")
    schedule.setdefault("end_time", "17:00")
    schedule.setdefault("timezone", "MST (Mountain Standard Time)")
    settings["schedule"] = schedule

    if "daily_limit" not in settings:
        settings["daily_limit"] = Config.MAX_EMAILS_PER_DAY
    if "follow_up_delay_days" not in settings:
        settings["follow_up_delay_days"] = 4
    if "on_hold" not in settings:
        settings["on_hold"] = False

    campaign["settings"] = settings


def normalize_campaign_stats(campaign: dict) -> None:
    stats = campaign.get("stats") or {}
    scheduled = stats.get("scheduled")

    output_file = campaign.get("output_file")
    if output_file:
        output_path = BASE_DIR / output_file
        if output_path.exists():
            try:
                scheduled = len(pd.read_csv(output_path))
            except Exception:
                scheduled = scheduled if scheduled is not None else 0

    stats["scheduled"] = int(scheduled or 0)
    for key in ["sent", "delivered", "opened", "replied", "successful", "bounced", "unsubscribed"]:
        if key not in stats:
            stats[key] = 0

    events_list = [e for e in load_events() if e.get("campaign_id") == campaign.get("id")]
    positive_classes = {"Positive interest", "Soft interest"}
    counters = {
        "sent": 0,
        "delivered": 0,
        "opened": 0,
        "replied": 0,
        "successful": 0,
        "bounced": 0,
        "unsubscribed": 0
    }

    for event in events_list:
        apply_event_to_bucket(counters, event, positive_classes)

    for key, value in counters.items():
        stats[key] = value

    campaign["stats"] = stats


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_port() -> int:
    env_port = os.getenv("PORT")
    if env_port and env_port.isdigit():
        env_value = int(env_port)
        if is_port_available(env_value):
            return env_value

    for candidate in (7000, 7001, 7010, 7050, 8000):
        if is_port_available(candidate):
            return candidate

    return 0


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route("/api/auth/register", methods=["POST"])
def register():
    """Register a new user (public endpoint)."""
    data = request.json

    if not data:
        return jsonify({"error": "Request body required"}), 400

    result = create_user(
        username=data.get("username"),
        email=data.get("email"),
        password=data.get("password"),
        full_name=data.get("full_name")
    )

    if result["success"]:
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@app.route("/api/auth/login", methods=["POST"])
def login():
    """Login with username/email and password."""
    data = request.json

    if not data:
        return jsonify({"error": "Request body required"}), 400

    result = authenticate_user(
        username_or_email=data.get("username"),
        password=data.get("password")
    )

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 401


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def get_current_user():
    """Get current user info from token."""
    return jsonify(request.current_user)


@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def logout():
    """Logout (client-side token removal)."""
    return jsonify({"success": True, "message": "Logged out"})


@app.route("/api/auth/change-password", methods=["POST"])
@require_auth
def change_user_password():
    """Change current user's password."""
    data = request.json

    if not data:
        return jsonify({"error": "Request body required"}), 400

    result = change_password(
        user_id=request.current_user["id"],
        old_password=data.get("old_password"),
        new_password=data.get("new_password")
    )

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 400


@app.route("/api/users", methods=["GET"])
@require_admin
def list_users():
    """List all users (admin only)."""
    users = get_all_users()
    return jsonify({"users": users})


@app.route("/api/users/<int:user_id>", methods=["PUT"])
@require_admin
def update_user_endpoint(user_id):
    """Update user (admin only)."""
    data = request.json

    if not data:
        return jsonify({"error": "Request body required"}), 400

    result = update_user(user_id, **data)

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 400


# ============================================================================
# CAMPAIGN ENDPOINTS (Protected)
# ============================================================================

@app.route("/api/campaigns", methods=["GET", "POST"])
@require_auth
def campaigns():
    ensure_seed_data()
    data = load_json()

    if request.method == "POST":
        payload = get_request_json()
        name = payload.get("name", "").strip() or "New Campaign"
        campaign_id = payload.get("id") or f"campaign-{len(data['campaigns']) + 1}"
        campaign = build_default_campaign()
        campaign.update(
            {
                "id": campaign_id,
                "name": name,
                "status": payload.get("status", "draft"),
                "strategy": payload.get("strategy", "conventional"),  # NEW: conventional, semi_auto, full_auto
                "lead_source": payload.get("lead_source", ""),
                "output_file": payload.get("output_file", "")
            }
        )
        normalize_campaign_settings(campaign)
        normalize_campaign_stats(campaign)
        data["campaigns"].append(campaign)
        save_json(data)
        return jsonify(campaign), 201

    campaign_list = []
    for campaign in data.get("campaigns", []):
        normalize_campaign_settings(campaign)
        normalize_campaign_stats(campaign)
        campaign_list.append(
            {
                "id": campaign.get("id"),
                "name": campaign.get("name"),
                "status": campaign.get("status"),
                "created_at": campaign.get("created_at"),
                "lead_source": campaign.get("lead_source"),
                "stats": campaign.get("stats", {})
            }
        )
    save_json(data)
    return jsonify(campaign_list)


@app.route("/api/campaigns/<campaign_id>", methods=["GET", "PUT"])
def campaign_detail(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    if request.method == "PUT":
        payload = get_request_json()
        campaign.update(payload)
        normalize_campaign_settings(campaign)
        normalize_campaign_stats(campaign)
        save_json(data)
        return jsonify(campaign)

    normalize_campaign_settings(campaign)
    normalize_campaign_stats(campaign)
    save_json(data)
    return jsonify(campaign)


@app.route("/api/campaigns/<campaign_id>/content", methods=["PUT"])
def campaign_content(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    payload = get_request_json()
    sequence = payload.get("sequence")
    if sequence:
        campaign["sequence"] = sequence
        save_json(data)
    return jsonify(campaign.get("sequence", {}))


@app.route("/api/campaigns/<campaign_id>/settings", methods=["PUT"])
def campaign_settings(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    payload = get_request_json()
    settings = payload.get("settings")
    if settings:
        campaign["settings"] = settings
        normalize_campaign_settings(campaign)
        save_json(data)
    return jsonify(campaign.get("settings", {}))


@app.route("/api/campaigns/<campaign_id>/stats", methods=["GET"])
def campaign_stats(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)
    normalize_campaign_stats(campaign)
    save_json(data)
    return jsonify(campaign.get("stats", {}))


@app.route("/api/campaigns/<campaign_id>/upload", methods=["POST"])
def campaign_upload(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files are supported"}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = secure_filename(file.filename)
    upload_path = UPLOAD_DIR / f"{timestamp}_{safe_name}"
    file.save(upload_path)

    campaign["lead_source"] = relative_path(upload_path)
    normalize_campaign_stats(campaign)
    save_json(data)
    return jsonify(campaign)


@app.route("/api/campaigns/<campaign_id>/generate", methods=["POST"])
def campaign_generate(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    payload = get_request_json()
    limit = payload.get("limit")
    output_name = (payload.get("output_name") or "").strip()
    if not output_name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"campaign_{campaign_id}_{timestamp}.csv"

    if not output_name.lower().endswith(".csv"):
        output_name += ".csv"

    lead_source = campaign.get("lead_source")
    if not lead_source:
        return jsonify({"error": "No lead source configured"}), 400

    input_path = BASE_DIR / lead_source
    if not input_path.exists():
        return jsonify({"error": "Lead source file not found"}), 400

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / secure_filename(output_name)

    try:
        strategy = campaign.get("strategy", "conventional")
        generate_campaigns(
            str(input_path),
            str(output_path),
            limit=int(limit) if limit else None,
            raise_on_error=True,
            strategy=strategy
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    campaign["output_file"] = relative_path(output_path)
    normalize_campaign_stats(campaign)
    stats = campaign.get("stats", {})
    stats["sent"] = 0
    stats["delivered"] = 0
    stats["opened"] = 0
    stats["replied"] = 0
    stats["successful"] = 0
    stats["bounced"] = 0
    stats["unsubscribed"] = 0
    campaign["stats"] = stats

    save_json(data)
    return jsonify({"output_file": campaign["output_file"], "stats": campaign.get("stats", {})})


@app.route("/api/campaigns/<campaign_id>/enrich", methods=["POST"])
def campaign_enrich(campaign_id: str):
    """
    Enrich leads with Apollo.io data

    Request body:
    {
        "fields": ["person", "company", "job_postings", "intent_score"]
    }

    Returns:
    {
        "enriched_count": int,
        "failed_count": int,
        "new_columns": list[str],
        "enriched_file": str
    }
    """
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    payload = get_request_json()
    enrichment_fields = payload.get("fields", ["person", "company", "intent_score"])

    # Get source CSV path
    source_path = campaign.get("lead_source")
    if not source_path:
        return jsonify({"error": "No lead source uploaded"}), 400

    csv_path = BASE_DIR / source_path
    if not csv_path.exists():
        return jsonify({"error": "Lead source file not found"}), 404

    # Load CSV
    import pandas as pd
    df = pd.read_csv(csv_path)

    # Initialize Apollo client
    try:
        from apollo_enrichment import (
            ApolloEnricher,
            detect_wms_system,
            detect_equipment_signals
        )
        enricher = ApolloEnricher()
    except Exception as e:
        return jsonify({"error": f"Failed to initialize Apollo client: {str(e)}"}), 500

    enriched_count = 0
    failed_count = 0

    # Add enrichment columns
    df["apollo_title"] = ""
    df["apollo_seniority"] = ""
    df["apollo_email_status"] = ""
    df["apollo_phone"] = ""
    df["employee_count"] = 0
    df["estimated_revenue"] = ""
    df["technologies"] = ""
    df["wms_system"] = ""
    df["equipment_signals"] = ""
    df["job_postings_count"] = 0
    df["job_postings_relevant"] = 0
    df["intent_score"] = 0.0

    logger.info(f"Starting Apollo enrichment for {len(df)} leads...")

    for idx, row in df.iterrows():
        try:
            email = row.get("Email address", "")
            company = row.get("Company", "")
            full_name = row.get("Full name", "")

            # Parse name
            name_parts = str(full_name).split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""

            person_data = {}
            company_data = {}
            job_postings = []

            # Enrich person
            if "person" in enrichment_fields:
                person_data = enricher.enrich_person(email, first_name, last_name, company) or {}
                if person_data:
                    df.at[idx, "apollo_title"] = person_data.get("title", "")
                    df.at[idx, "apollo_seniority"] = person_data.get("seniority", "")
                    df.at[idx, "apollo_email_status"] = person_data.get("email_status", "")
                    df.at[idx, "apollo_phone"] = person_data.get("phone", "")

            # Enrich company
            if "company" in enrichment_fields:
                # Try to get domain from email
                domain = email.split("@")[1] if "@" in email else None
                company_data = enricher.enrich_company(company_name=company, domain=domain) or {}

                if company_data:
                    df.at[idx, "employee_count"] = company_data.get("employee_count", 0)
                    df.at[idx, "estimated_revenue"] = company_data.get("estimated_revenue", "")
                    technologies = company_data.get("technologies", [])
                    df.at[idx, "technologies"] = ", ".join(technologies)
                    df.at[idx, "wms_system"] = detect_wms_system(technologies)
                    df.at[idx, "equipment_signals"] = ", ".join(detect_equipment_signals(
                        technologies,
                        company_data.get("seo_description", "")
                    ))
                    df.at[idx, "job_postings_count"] = company_data.get("current_job_openings_count", 0)

            # Get job postings (intent signal)
            if "job_postings" in enrichment_fields and company_data.get("company_id"):
                job_postings = enricher.get_company_job_postings(company_data["company_id"])
                # Count relevant job postings
                warehouse_keywords = ['warehouse', 'distribution', 'supply chain', 'logistics',
                                    'automation', 'controls', 'engineering']
                relevant_jobs = [
                    job for job in job_postings
                    if any(kw in job.get('title', '').lower() for kw in warehouse_keywords)
                ]
                df.at[idx, "job_postings_relevant"] = len(relevant_jobs)

            # Calculate intent score
            if "intent_score" in enrichment_fields:
                intent_score = calculate_intent_score(person_data, company_data, job_postings)
                df.at[idx, "intent_score"] = round(intent_score, 2)

            enriched_count += 1
            logger.info(f"Enriched {enriched_count}/{len(df)}: {email}")

        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to enrich {email}: {e}")
            continue

    # Save enriched CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_filename = Path(source_path).stem
    enriched_filename = f"{timestamp}_{original_filename}_enriched.csv"
    enriched_path = UPLOAD_DIR / enriched_filename
    df.to_csv(enriched_path, index=False)

    # Update campaign with enriched file
    campaign["lead_source"] = relative_path(enriched_path)
    save_json(data)

    logger.info(f"Enrichment complete: {enriched_count} enriched, {failed_count} failed")

    return jsonify({
        "enriched_count": enriched_count,
        "failed_count": failed_count,
        "new_columns": [
            "apollo_title", "apollo_seniority", "employee_count", "estimated_revenue",
            "technologies", "wms_system", "equipment_signals", "intent_score"
        ],
        "enriched_file": str(enriched_path)
    })


@app.route("/api/apollo/search", methods=["POST"])
def apollo_search():
    payload = get_request_json()
    campaign_id = payload.get("campaign_id", "")
    search_payload = payload.get("search", {})
    min_icp_score = int(payload.get("min_icp_score", 1))
    allow_phone = bool(payload.get("allow_phone", False))
    allow_personal_emails = bool(payload.get("allow_personal_emails", False))

    if not search_payload:
        return jsonify({"error": "search payload is required"}), 400

    try:
        from apollo_enrichment import ApolloEnricher
        enricher = ApolloEnricher()
    except Exception as e:
        return jsonify({"error": f"Failed to initialize Apollo client: {str(e)}"}), 500

    people = enricher.search_people(search_payload)
    stats = {
        "discovered": len(people),
        "accepted": 0,
        "queued": 0,
        "skipped": 0,
        "suppressed": 0,
        "rejected": 0
    }

    for person in people:
        person_record, company_record = parse_apollo_search_person(person)
        company_key = upsert_company(company_record)
        person_record["company_key"] = company_key
        person_record["company_domain"] = company_record.get("domain", "")

        features = extract_features(person_record, company_record)
        icp_match, icp_score, _ = score_icp(features)
        readiness_score = compute_automation_readiness(features)
        strategy_assignment = assign_strategy(icp_match, readiness_score)

        person_record.update(
            {
                "icp_match": icp_match,
                "icp_score": icp_score,
                "readiness_score": readiness_score,
                "strategy_assignment": strategy_assignment,
                "source": "apollo_search"
            }
        )

        person_key = upsert_person(person_record)
        person_row = get_person_by_key(person_key) or {}

        if icp_score < min_icp_score:
            insert_queue_record(
                person_key,
                campaign_id,
                "rejected",
                "",
                False,
                False,
                note="icp_score_below_threshold"
            )
            stats["rejected"] += 1
            continue

        stats["accepted"] += 1

        if is_suppressed(person_key):
            insert_queue_record(
                person_key,
                campaign_id,
                "suppressed",
                "",
                False,
                False,
                note="suppression_window"
            )
            stats["suppressed"] += 1
            continue

        needs_enrichment = person_enrichment_needed(person_row)
        reveal_phone_number = bool(allow_phone and icp_match in {"ICP 4", "ICP 5"})
        request_hash = calculate_enrichment_hash(person_key, allow_personal_emails, reveal_phone_number)

        if not needs_enrichment:
            insert_queue_record(
                person_key,
                campaign_id,
                "skipped",
                request_hash,
                allow_personal_emails,
                reveal_phone_number,
                note="already_enriched"
            )
            stats["skipped"] += 1
            continue

        if recent_request_hash(person_key, request_hash, Config.APOLLO_PERSON_TTL_DAYS):
            insert_queue_record(
                person_key,
                campaign_id,
                "skipped",
                request_hash,
                allow_personal_emails,
                reveal_phone_number,
                note="recent_request"
            )
            stats["skipped"] += 1
            continue

        enqueue_enrichment(
            person_key,
            campaign_id,
            request_hash,
            allow_personal_emails,
            reveal_phone_number,
            note="queued_for_enrichment"
        )
        stats["queued"] += 1

    return jsonify(stats)


@app.route("/api/apollo/queue", methods=["GET"])
def apollo_queue():
    campaign_id = request.args.get("campaign_id", "")
    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    summary = get_queue_summary(campaign_id)
    items = get_queue_items(status, limit) if status else []
    return jsonify({"summary": summary, "items": items})


@app.route("/api/apollo/queue/process", methods=["POST"])
def apollo_queue_process():
    payload = get_request_json()
    limit = int(payload.get("limit", Config.APOLLO_BULK_MATCH_SIZE))
    include_job_postings = bool(payload.get("include_job_postings", False))

    try:
        from apollo_enrichment import (
            ApolloEnricher,
            calculate_intent_score,
            detect_wms_system,
            detect_equipment_signals
        )
        enricher = ApolloEnricher()
    except Exception as e:
        return jsonify({"error": f"Failed to initialize Apollo client: {str(e)}"}), 500

    items = get_queue_items("queued", limit)
    if not items:
        return jsonify({"processed": 0, "message": "No queued records"}), 200

    processed = 0
    failed = 0

    grouped = {}
    for item in items:
        key = (item.get("reveal_personal_emails", 0), item.get("reveal_phone_number", 0))
        grouped.setdefault(key, []).append(item)

    for (reveal_personal, reveal_phone), group_items in grouped.items():
        for i in range(0, len(group_items), Config.APOLLO_BULK_MATCH_SIZE):
            batch = group_items[i:i + Config.APOLLO_BULK_MATCH_SIZE]
            details = []
            item_lookup = {}

            for item in batch:
                person_row = get_person_by_key(item.get("person_key"))
                if not person_row:
                    update_queue_status(item["id"], "failed", "missing_person")
                    failed += 1
                    continue
                company_row = get_company_by_key(person_row.get("company_key", ""))
                details.append(
                    {
                        "email": person_row.get("email", ""),
                        "first_name": person_row.get("first_name", ""),
                        "last_name": person_row.get("last_name", ""),
                        "organization_name": company_row.get("name", "") if company_row else "",
                        "domain": company_row.get("domain_norm", "") if company_row else "",
                        "linkedin_url": person_row.get("linkedin_url_norm", ""),
                        "person_id": person_row.get("apollo_person_id", "")
                    }
                )
                item_lookup[item["id"]] = {"person": person_row, "company": company_row, "queue": item}

            if not details:
                continue

            response_people = enricher.bulk_enrich_people(
                details,
                reveal_personal_emails=bool(reveal_personal),
                reveal_phone_number=bool(reveal_phone)
            )

            response_by_id = {}
            response_by_email = {}
            response_by_linkedin = {}
            for person in response_people:
                person_id = person.get("id")
                if person_id:
                    response_by_id[str(person_id)] = person
                email_norm = normalize_scoring_text(person.get("email", ""))
                if email_norm:
                    response_by_email[email_norm] = person
                linkedin_norm = normalize_scoring_text(person.get("linkedin_url", ""))
                if linkedin_norm:
                    response_by_linkedin[linkedin_norm] = person

            for entry in item_lookup.values():
                person_row = entry["person"]
                company_row = entry["company"] or {}
                queue_item = entry["queue"]

                match = None
                if person_row.get("apollo_person_id"):
                    match = response_by_id.get(str(person_row.get("apollo_person_id")))
                if not match and person_row.get("email_norm"):
                    match = response_by_email.get(person_row.get("email_norm"))
                if not match and person_row.get("linkedin_url_norm"):
                    match = response_by_linkedin.get(person_row.get("linkedin_url_norm"))

                if not match:
                    update_queue_status(queue_item["id"], "failed", "no_match")
                    failed += 1
                    continue

                person_update, company_update = parse_apollo_person_response(match)
                company_payload = {}
                if company_row:
                    company_payload = {
                        "apollo_org_id": company_row.get("apollo_org_id", ""),
                        "company_id": company_row.get("apollo_org_id", ""),
                        "name": company_row.get("name", ""),
                        "domain": company_row.get("domain_norm", ""),
                        "industry": company_row.get("industry", ""),
                        "employee_count": company_row.get("employee_count", 0),
                        "estimated_revenue": company_row.get("estimated_revenue", ""),
                        "technologies": [item.strip() for item in str(company_row.get("technologies", "")).split(",") if item.strip()],
                        "wms_system": company_row.get("wms_system", ""),
                        "equipment_signals": [item.strip() for item in str(company_row.get("equipment_signals", "")).split(",") if item.strip()],
                        "job_postings_count": company_row.get("job_postings_count", 0),
                        "job_postings_relevant": company_row.get("job_postings_relevant", 0),
                        "locations": [item.strip() for item in str(company_row.get("locations", "")).split(",") if item.strip()],
                        "enriched_at": company_row.get("enriched_at")
                    }
                company_payload.update(company_update)

                if company_enrichment_needed(company_row):
                    enriched_company = enricher.enrich_company(
                        company_name=company_update.get("name") or company_row.get("name"),
                        domain=company_update.get("domain") or company_row.get("domain_norm")
                    ) or {}
                    if enriched_company:
                        company_payload.update(
                            {
                                "apollo_org_id": enriched_company.get("company_id", ""),
                                "company_id": enriched_company.get("company_id", ""),
                                "name": enriched_company.get("name", "") or company_payload.get("name", ""),
                                "domain": enriched_company.get("domain", "") or company_payload.get("domain", ""),
                                "industry": enriched_company.get("industry", "") or company_payload.get("industry", ""),
                                "employee_count": enriched_company.get("employee_count", 0) or company_payload.get("employee_count", 0),
                                "estimated_revenue": enriched_company.get("estimated_revenue", ""),
                                "technologies": enriched_company.get("technologies", []),
                                "job_postings_count": enriched_company.get("current_job_openings_count", 0),
                                "enriched_at": utc_now()
                            }
                        )

                        if include_job_postings and enriched_company.get("company_id"):
                            job_postings = enricher.get_company_job_postings(enriched_company["company_id"])
                            warehouse_keywords = ['warehouse', 'distribution', 'supply chain', 'logistics',
                                                'automation', 'controls', 'engineering']
                            relevant_jobs = [
                                job for job in job_postings
                                if any(kw in job.get('title', '').lower() for kw in warehouse_keywords)
                            ]
                            company_payload["job_postings_relevant"] = len(relevant_jobs)
                            company_payload["controls_roles_hiring"] = any(
                                "controls" in job.get("title", "").lower() for job in job_postings
                            )

                technologies = company_payload.get("technologies", [])
                company_payload["wms_system"] = detect_wms_system(technologies)
                company_payload["equipment_signals"] = detect_equipment_signals(
                    technologies,
                    ""
                )

                company_key = upsert_company(company_payload)

                person_payload = {}
                person_payload.update(person_update)
                person_payload["company_key"] = company_key
                person_payload["company_domain"] = company_payload.get("domain", "")
                person_payload["enriched_at"] = utc_now()
                person_payload["enrichment_request_hash"] = queue_item.get("request_hash", "")

                features = extract_features(person_payload, company_payload)
                icp_match, icp_score, _ = score_icp(features)
                readiness_score = compute_automation_readiness(features)
                strategy_assignment = assign_strategy(icp_match, readiness_score)

                person_payload.update(
                    {
                        "icp_match": icp_match,
                        "icp_score": icp_score,
                        "readiness_score": readiness_score,
                        "strategy_assignment": strategy_assignment
                    }
                )

                upsert_person(person_payload)
                update_queue_status(queue_item["id"], "enriched")
                processed += 1

    return jsonify({"processed": processed, "failed": failed})


@app.route("/api/apollo/credit-estimate", methods=["POST"])
def apollo_credit_estimate():
    payload = get_request_json()
    return jsonify(build_credit_estimate(payload))


@app.route("/api/campaigns/<campaign_id>/apollo/export", methods=["POST"])
def campaign_apollo_export(campaign_id: str):
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    leads = get_people_for_campaign(campaign_id)
    if not leads:
        return jsonify({"error": "No enriched leads available for export"}), 400

    rows = []
    for lead in leads:
        full_name = " ".join([lead.get("first_name", ""), lead.get("last_name", "")]).strip()
        rows.append(
            {
                "Company": lead.get("company_name", ""),
                "Industry": lead.get("company_industry", ""),
                "Email address": lead.get("email", ""),
                "Full name": full_name,
                "Job title": lead.get("title", ""),
                "ICP Match": lead.get("icp_match", ""),
                "Notes": "",
                "Equipment": lead.get("equipment_signals", ""),
                "strategy_assignment": lead.get("strategy_assignment", ""),
                "employee_count": lead.get("employee_count", 0),
                "technologies": lead.get("technologies", ""),
                "wms_system": lead.get("wms_system", ""),
                "job_postings_relevant": lead.get("job_postings_relevant", 0)
            }
        )

    df = pd.DataFrame(rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_filename = f"{timestamp}_apollo_campaign_{campaign_id}.csv"
    export_path = UPLOAD_DIR / export_filename
    df.to_csv(export_path, index=False)

    campaign["lead_source"] = relative_path(export_path)
    save_json(data)

    return jsonify(
        {
            "lead_source": campaign["lead_source"],
            "row_count": len(df)
        }
    )


@app.route("/api/events", methods=["GET", "POST"])
def events():
    if request.method == "POST":
        payload = get_request_json()
        event_type = payload.get("event_type")
        campaign_id = payload.get("campaign_id")
        if not event_type or not campaign_id:
            return jsonify({"error": "event_type and campaign_id are required"}), 400

        event = {
            "event_type": event_type,
            "campaign_id": campaign_id,
            "email_sequence": payload.get("email_sequence"),
            "sender_email": payload.get("sender_email", ""),
            "recipient_email": payload.get("recipient_email", ""),
            "icp_segment": payload.get("icp_segment", ""),
            "pain_theme": payload.get("pain_theme", ""),
            "cta_variant_id": payload.get("cta_variant_id", ""),
            "subject_variant_id": payload.get("subject_variant_id", ""),
            "personalization_hash": payload.get("personalization_hash", ""),
            "reply_class": payload.get("reply_class", "")
        }

        data = load_json()
        campaign = find_campaign(data, campaign_id)
        if campaign:
            event = enrich_event(event, campaign)

        stored = append_event(event)
        return jsonify(stored), 201

    campaign_id = request.args.get("campaign_id")
    event_type = request.args.get("event_type")
    dimension = request.args.get("dimension")
    value = request.args.get("value")
    limit = int(request.args.get("limit", 200))

    events_list = load_events()
    if campaign_id:
        events_list = [e for e in events_list if e.get("campaign_id") == campaign_id]
    if event_type:
        events_list = [e for e in events_list if e.get("event_type") == event_type]
    if dimension and value:
        if dimension in {"hour", "day"}:
            filtered = []
            for event in events_list:
                timestamp = parse_timestamp(event.get("timestamp", ""))
                if not timestamp:
                    continue
                if dimension == "hour" and timestamp.strftime("%H:00") == value:
                    filtered.append(event)
                if dimension == "day" and timestamp.strftime("%a") == value:
                    filtered.append(event)
            events_list = filtered
        else:
            events_list = [e for e in events_list if str(e.get(dimension, "")) == value]

    events_list.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return jsonify({"events": events_list[:limit]})


@app.route("/api/simulate", methods=["POST"])
def simulate_events():
    payload = get_request_json()
    campaign_id = payload.get("campaign_id")
    if not campaign_id:
        return jsonify({"error": "campaign_id is required"}), 400

    count = int(payload.get("count", 50))
    open_rate = float(payload.get("open_rate", 0.25))
    reply_rate = float(payload.get("reply_rate", 0.05))
    bounce_rate = float(payload.get("bounce_rate", 0.01))
    unsubscribe_rate = float(payload.get("unsubscribe_rate", 0.005))
    click_rate = float(payload.get("click_rate", 0.02))
    positive_rate = float(payload.get("positive_rate", 0.4))

    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    output_file = campaign.get("output_file")
    if not output_file:
        return jsonify({"error": "Campaign has no output file"}), 400

    output_path = BASE_DIR / output_file
    if not output_path.exists():
        return jsonify({"error": "Output file not found"}), 400

    try:
        df = pd.read_csv(output_path)
    except Exception as exc:
        return jsonify({"error": f"Failed to read output file: {exc}"}), 500

    if df.empty:
        return jsonify({"error": "Output file has no rows"}), 400

    count = max(1, min(count, len(df)))
    seed_text = payload.get("seed") or f"{campaign_id}-{count}"
    seed_value = int(hashlib.md5(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    sample = df.sample(n=count, random_state=seed_value)

    base_time = datetime.now(timezone.utc) - timedelta(minutes=count)
    replies_list = load_replies()
    created = 0

    for idx, row in enumerate(sample.to_dict(orient="records")):
        recipient = str(row.get("recipient_email", ""))
        sequence = row.get("email_sequence", 1)
        base = build_event_base(row, campaign_id)
        timestamp = (base_time + timedelta(minutes=idx)).isoformat()
        seed_prefix = f"{recipient}|{sequence}"

        append_event({**base, "event_type": "email_sent", "timestamp": timestamp})
        created += 1

        bounced = deterministic_hit(f"{seed_prefix}|bounce", bounce_rate)
        if bounced:
            append_event({**base, "event_type": "email_bounced", "timestamp": timestamp})
            created += 1
            continue

        append_event({**base, "event_type": "email_delivered", "timestamp": timestamp})
        created += 1

        if deterministic_hit(f"{seed_prefix}|unsub", unsubscribe_rate):
            append_event({**base, "event_type": "email_unsubscribed", "timestamp": timestamp})
            created += 1

        opened = deterministic_hit(f"{seed_prefix}|open", open_rate)
        if opened:
            append_event({**base, "event_type": "email_opened", "timestamp": timestamp})
            created += 1

        if opened and deterministic_hit(f"{seed_prefix}|click", click_rate):
            append_event({**base, "event_type": "email_clicked", "timestamp": timestamp})
            created += 1

        replied = deterministic_hit(f"{seed_prefix}|reply", reply_rate)
        if replied:
            append_event({**base, "event_type": "email_replied", "timestamp": timestamp})
            created += 1

            positive = deterministic_hit(f"{seed_prefix}|positive", positive_rate)
            reply_class = (
                deterministic_choice(seed_prefix, ["Positive interest", "Soft interest"])
                if positive
                else deterministic_choice(seed_prefix, ["Neutral / info", "Objection"])
            )

            scores = {
                "Positive interest": (0.85, 0.9),
                "Soft interest": (0.65, 0.6),
                "Neutral / info": (0.5, 0.4),
                "Objection": (0.3, 0.2)
            }
            sentiment_score, intent_score = scores.get(reply_class, (0.5, 0.4))

            replies_list.append(
                {
                    "reply_id": str(uuid.uuid4()),
                    "timestamp": timestamp,
                    "campaign_id": campaign_id,
                    "recipient_email": recipient,
                    "sender_email": safe_value(row.get("sender_email", "")),
                    "email_sequence": sequence,
                    "reply_text": f"Simulated reply ({reply_class})",
                    "reply_class": reply_class,
                    "sentiment_score": sentiment_score,
                    "intent_score": intent_score
                }
            )

            append_event(
                {
                    **base,
                    "event_type": "reply_classified",
                    "timestamp": timestamp,
                    "reply_class": reply_class
                }
            )
            created += 1

    save_replies(replies_list)
    normalize_campaign_stats(campaign)
    save_json(data)

    return jsonify({"events_created": created})


@app.route("/api/replies", methods=["POST"])
def replies():
    payload = get_request_json()
    campaign_id = payload.get("campaign_id")
    recipient_email = payload.get("recipient_email")
    reply_text = payload.get("reply_text")
    sender_email = payload.get("sender_email", "")
    email_sequence = payload.get("email_sequence")

    if not campaign_id or not recipient_email or not reply_text:
        return jsonify({"error": "campaign_id, recipient_email, and reply_text are required"}), 400

    classification = classify_reply_text(reply_text)
    reply_record = {
        "reply_id": str(uuid.uuid4()),
        "timestamp": utc_now(),
        "campaign_id": campaign_id,
        "recipient_email": recipient_email,
        "sender_email": sender_email,
        "email_sequence": email_sequence,
        "reply_text": reply_text,
        **classification
    }

    replies_list = load_replies()
    replies_list.append(reply_record)
    save_replies(replies_list)

    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if campaign:
        base_event = {
            "campaign_id": campaign_id,
            "recipient_email": recipient_email,
            "sender_email": sender_email,
            "email_sequence": email_sequence,
            "reply_class": classification["reply_class"]
        }
        append_event(enrich_event({**base_event, "event_type": "email_replied"}, campaign))
        append_event(enrich_event({**base_event, "event_type": "reply_classified"}, campaign))

    return jsonify(reply_record), 201


def initialize_breakdown() -> dict:
    return {
        "sent": 0,
        "delivered": 0,
        "opened": 0,
        "replied": 0,
        "successful": 0,
        "bounced": 0,
        "unsubscribed": 0
    }


def apply_event_to_bucket(bucket: dict, event: dict, positive_classes: set[str]) -> None:
    event_type = event.get("event_type")
    if event_type == "email_sent":
        bucket["sent"] += 1
    elif event_type == "email_delivered":
        bucket["delivered"] += 1
    elif event_type == "email_opened":
        bucket["opened"] += 1
    elif event_type == "email_replied":
        bucket["replied"] += 1
    elif event_type == "email_bounced":
        bucket["bounced"] += 1
    elif event_type == "email_unsubscribed":
        bucket["unsubscribed"] += 1
    elif event_type == "reply_classified":
        if event.get("reply_class") in positive_classes:
            bucket["successful"] += 1


def compute_response_latencies(events_list: list[dict]) -> list[float]:
    sent_times: dict[str, datetime] = {}
    latencies: list[float] = []

    for event in events_list:
        event_type = event.get("event_type")
        recipient = event.get("recipient_email", "")
        sequence = event.get("email_sequence", "")
        key = f"{recipient}|{sequence}"

        if event_type == "email_sent":
            timestamp = parse_timestamp(event.get("timestamp", ""))
            if timestamp:
                sent_times[key] = timestamp

        if event_type == "email_replied":
            timestamp = parse_timestamp(event.get("timestamp", ""))
            if timestamp and key in sent_times:
                delta = timestamp - sent_times[key]
                latencies.append(delta.total_seconds() / 3600)

    return latencies


def build_strategy_rollup() -> dict:
    return {
        "sent": 0,
        "delivered": 0,
        "opened": 0,
        "replied": 0,
        "successful": 0,
        "bounced": 0,
        "unsubscribed": 0,
        "intent_sum": 0.0,
        "intent_count": 0,
        "latencies": []
    }


def regularized_gamma_q(a: float, x: float, eps: float = 1e-12, max_iter: int = 200) -> float:
    if x <= 0 or a <= 0:
        return 1.0

    if x < a + 1.0:
        ap = a
        sum_value = 1.0 / a
        delta = sum_value
        for _ in range(max_iter):
            ap += 1.0
            delta *= x / ap
            sum_value += delta
            if abs(delta) < abs(sum_value) * eps:
                break
        p = sum_value * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return max(0.0, min(1.0, 1.0 - p))

    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break

    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return max(0.0, min(1.0, q))


def chi_square_p_value(statistic: float, df: int) -> float | None:
    if df <= 0 or statistic < 0:
        return None
    return regularized_gamma_q(df / 2.0, statistic / 2.0)


def calculate_strategy_comparison() -> dict:
    data = load_json()
    campaigns = data.get("campaigns", [])
    campaign_map = {c.get("id"): c for c in campaigns if c.get("id")}

    events_list = load_events()
    replies_list = load_replies()

    events_by_campaign: dict[str, list[dict]] = {}
    for event in events_list:
        campaign_id = event.get("campaign_id")
        if not campaign_id or campaign_id not in campaign_map:
            continue
        events_by_campaign.setdefault(campaign_id, []).append(event)

    replies_by_campaign: dict[str, list[dict]] = {}
    for reply in replies_list:
        campaign_id = reply.get("campaign_id")
        if not campaign_id or campaign_id not in campaign_map:
            continue
        replies_by_campaign.setdefault(campaign_id, []).append(reply)

    positive_classes = {"Positive interest", "Soft interest"}
    strategy_rollups: dict[str, dict] = {}
    strategy_campaigns: dict[str, int] = {}

    for campaign in campaigns:
        campaign_id = campaign.get("id")
        if not campaign_id:
            continue
        strategy = campaign.get("strategy", "conventional")
        rollup = strategy_rollups.setdefault(strategy, build_strategy_rollup())
        strategy_campaigns[strategy] = strategy_campaigns.get(strategy, 0) + 1

        counters = initialize_breakdown()
        campaign_events = events_by_campaign.get(campaign_id, [])
        for event in campaign_events:
            apply_event_to_bucket(counters, event, positive_classes)

        for key in ["sent", "delivered", "opened", "replied", "successful", "bounced", "unsubscribed"]:
            rollup[key] += counters[key]

        rollup["latencies"].extend(compute_response_latencies(campaign_events))

        for reply in replies_by_campaign.get(campaign_id, []):
            try:
                rollup["intent_sum"] += float(reply.get("intent_score", 0) or 0)
                rollup["intent_count"] += 1
            except (TypeError, ValueError):
                continue

    for strategy in ("conventional", "semi_auto", "full_auto"):
        strategy_rollups.setdefault(strategy, build_strategy_rollup())
        strategy_campaigns.setdefault(strategy, 0)

    strategies = {}
    for strategy, rollup in strategy_rollups.items():
        base = rollup["delivered"] or rollup["sent"]
        reply_rate = rollup["replied"] / base if base else 0
        positive_rate = rollup["successful"] / rollup["replied"] if rollup["replied"] else 0
        avg_intent = (
            rollup["intent_sum"] / rollup["intent_count"] if rollup["intent_count"] else 0
        )
        latencies = rollup["latencies"]
        avg_response_hours = sum(latencies) / len(latencies) if latencies else 0

        strategies[strategy] = {
            "campaigns": strategy_campaigns.get(strategy, 0),
            "sent": rollup["sent"],
            "delivered": rollup["delivered"],
            "replied": rollup["replied"],
            "successful": rollup["successful"],
            "reply_rate": reply_rate,
            "positive_rate": positive_rate,
            "avg_intent": avg_intent,
            "avg_response_hours": avg_response_hours,
            "base": base
        }

    eligible = [
        (strategy, data)
        for strategy, data in strategies.items()
        if data.get("base", 0) > 0
    ]

    chi_square = {
        "statistic": None,
        "p_value": None,
        "df": None,
        "alpha": 0.05,
        "significant": False,
        "eligible_strategies": [strategy for strategy, _ in eligible],
        "note": ""
    }

    if len(eligible) >= 2:
        replied_counts = [data.get("replied", 0) for _, data in eligible]
        non_replied_counts = [
            max(0, data.get("base", 0) - data.get("replied", 0)) for _, data in eligible
        ]
        row_totals = [sum(replied_counts), sum(non_replied_counts)]
        grand_total = sum(row_totals)
        if grand_total > 0:
            chi2 = 0.0
            for col_idx in range(len(eligible)):
                col_total = replied_counts[col_idx] + non_replied_counts[col_idx]
                if col_total == 0:
                    continue
                expected_replied = row_totals[0] * col_total / grand_total
                expected_non_replied = row_totals[1] * col_total / grand_total
                if expected_replied > 0:
                    chi2 += (replied_counts[col_idx] - expected_replied) ** 2 / expected_replied
                if expected_non_replied > 0:
                    chi2 += (
                        (non_replied_counts[col_idx] - expected_non_replied) ** 2
                        / expected_non_replied
                    )

            df = len(eligible) - 1
            p_value = chi_square_p_value(chi2, df)
            chi_square.update(
                {
                    "statistic": chi2,
                    "p_value": p_value,
                    "df": df,
                    "significant": bool(p_value is not None and p_value < chi_square["alpha"])
                }
            )
        else:
            chi_square["note"] = "Not enough delivered volume for comparison."
    else:
        chi_square["note"] = "Need at least two strategies with delivered volume."

    return {"strategies": strategies, "chi_square": chi_square}


@app.route("/api/metrics/strategy-comparison")
def strategy_comparison_metrics():
    return jsonify(calculate_strategy_comparison())


@app.route("/api/metrics")
def metrics():
    campaign_id = request.args.get("campaign_id")
    if not campaign_id:
        return jsonify({"error": "campaign_id is required"}), 400

    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    normalize_campaign_stats(campaign)
    save_json(data)

    events_list = [e for e in load_events() if e.get("campaign_id") == campaign_id]
    positive_classes = {"Positive interest", "Soft interest"}

    funnel = initialize_breakdown()
    for event in events_list:
        apply_event_to_bucket(funnel, event, positive_classes)

    funnel["scheduled"] = campaign.get("stats", {}).get("scheduled", 0)

    breakdowns = {
        "sender": {},
        "icp": {},
        "pain_theme": {},
        "cta_variant": {},
        "subject_variant": {}
    }

    reply_classes = {}
    sent_times = {}
    response_latencies = []
    day_counts = {}
    hour_counts = {}

    for event in events_list:
        event_type = event.get("event_type")
        recipient = event.get("recipient_email", "")
        sequence = event.get("email_sequence", "")
        key = f"{recipient}|{sequence}"

        if event_type == "email_sent":
            timestamp = parse_timestamp(event.get("timestamp", ""))
            if timestamp:
                sent_times[key] = timestamp
                day = timestamp.strftime("%a")
                hour = timestamp.strftime("%H:00")
                day_counts[day] = day_counts.get(day, 0) + 1
                hour_counts[hour] = hour_counts.get(hour, 0) + 1

        if event_type == "email_replied":
            timestamp = parse_timestamp(event.get("timestamp", ""))
            if timestamp and key in sent_times:
                delta = timestamp - sent_times[key]
                response_latencies.append(delta.total_seconds() / 3600)

        if event_type == "reply_classified":
            reply_class = event.get("reply_class") or "Unknown"
            reply_classes[reply_class] = reply_classes.get(reply_class, 0) + 1

        for dimension, field in [
            ("sender", "sender_email"),
            ("icp", "icp_segment"),
            ("pain_theme", "pain_theme"),
            ("cta_variant", "cta_variant_id"),
            ("subject_variant", "subject_variant_id")
        ]:
            value = event.get(field) or "Unknown"
            bucket = breakdowns[dimension].setdefault(value, initialize_breakdown())
            apply_event_to_bucket(bucket, event, positive_classes)

    avg_latency = sum(response_latencies) / len(response_latencies) if response_latencies else 0
    replies_list = [r for r in load_replies() if r.get("campaign_id") == campaign_id]
    if replies_list:
        avg_sentiment = sum(r.get("sentiment_score", 0) for r in replies_list) / len(replies_list)
        avg_intent = sum(r.get("intent_score", 0) for r in replies_list) / len(replies_list)
    else:
        avg_sentiment = 0
        avg_intent = 0

    return jsonify(
        {
            "funnel": funnel,
            "breakdowns": {
                key: [
                    {"key": dim, **stats}
                    for dim, stats in sorted(value.items(), key=lambda item: item[1]["sent"], reverse=True)
                ]
                for key, value in breakdowns.items()
            },
            "reply_classes": [
                {"class": cls, "count": count}
                for cls, count in sorted(reply_classes.items(), key=lambda item: item[1], reverse=True)
            ],
            "time": {
                "by_day": [
                    {"day": day, "sent": count}
                    for day, count in sorted(day_counts.items(), key=lambda item: item[0])
                ],
                "by_hour": [
                    {"hour": hour, "sent": count}
                    for hour, count in sorted(hour_counts.items(), key=lambda item: item[0])
                ]
            },
            "quality": {
                "avg_sentiment": avg_sentiment,
                "avg_intent": avg_intent,
                "avg_latency_hours": avg_latency
            }
        }
    )


@app.route("/api/campaigns/<campaign_id>/audience")
def campaign_audience(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    limit = int(request.args.get("limit", 250))
    source_path = campaign.get("lead_source")
    if not source_path:
        return jsonify({"rows": [], "total": 0})

    csv_path = BASE_DIR / source_path
    if not csv_path.exists():
        return jsonify({"rows": [], "total": 0})

    df = pd.read_csv(csv_path)
    total = len(df)
    df = df.head(limit)

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "name": safe_value(row.get("Full name", "")),
                "email": safe_value(row.get("Email address", "")),
                "company": safe_value(row.get("Company", "")),
                "title": safe_value(row.get("Job title", "")),
                "industry": safe_value(row.get("Industry", ""))
            }
        )

    return jsonify({"rows": rows, "total": total})


@app.route("/api/campaigns/<campaign_id>/emails")
def campaign_emails(campaign_id: str):
    ensure_seed_data()
    data = load_json()
    campaign = find_campaign(data, campaign_id)
    if not campaign:
        abort(404)

    limit = int(request.args.get("limit", 200))
    output_file = campaign.get("output_file")
    if not output_file:
        return jsonify({"rows": [], "total": 0})

    csv_path = BASE_DIR / output_file
    if not csv_path.exists():
        return jsonify({"rows": [], "total": 0})

    df = pd.read_csv(csv_path)
    total = len(df)
    df = df.head(limit)

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "sequence": int(row.get("email_sequence", 1)) if pd.notna(row.get("email_sequence", 1)) else 1,
                "subject": safe_value(row.get("subject", "")),
                "body": safe_value(row.get("body", "")),
                "sender": safe_value(row.get("sender_name", "")),
                "sender_email": safe_value(row.get("sender_email", "")),
                "recipient": safe_value(row.get("recipient_email", ""))
            }
        )

    return jsonify({"rows": rows, "total": total})


@app.route("/api/senders")
def senders():
    """Get all sender profiles with signatures and personas from database."""
    from lead_registry import get_connection

    conn = get_connection()
    try:
        senders = conn.execute("SELECT * FROM sender_signatures ORDER BY full_name").fetchall()
        sender_list = [dict(s) for s in senders]

        # If no senders in DB, return config profiles
        if not sender_list:
            for profile in Config.SENDER_PROFILES:
                sender_list.append({
                    "email": profile["email"],
                    "full_name": profile["full_name"],
                    "title": profile["title"],
                    "phone": profile.get("phone", ""),
                    "company": profile.get("company", "Intralog"),
                    "signature_html": profile.get("signature", ""),
                    "persona_context": ""
                })

        conn.close()
        return jsonify(sender_list)
    except Exception as e:
        logger.error(f"Failed to get senders: {e}")
        conn.close()
        # Fallback to config
        return jsonify([{
            "email": p["email"],
            "full_name": p["full_name"],
            "title": p["title"],
            "phone": p.get("phone", ""),
            "company": p.get("company", "Intralog"),
            "signature_html": p.get("signature", ""),
            "persona_context": ""
        } for p in Config.SENDER_PROFILES])


# ====================
# NEW ENDPOINTS: Signature Management & Sender CRUD
# ====================

@app.route("/api/senders", methods=["POST"])
def create_sender():
    """Create a new sender profile."""
    from lead_registry import get_connection, utc_now

    data = request.json
    email = data.get("email")
    full_name = data.get("full_name")

    if not email or not full_name:
        return jsonify({"error": "Email and full name are required"}), 400

    conn = get_connection()
    try:
        # Check if sender already exists
        existing = conn.execute("SELECT email FROM sender_signatures WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "Sender with this email already exists"}), 400

        # Insert new sender
        conn.execute("""
            INSERT INTO sender_signatures (
                email, full_name, title, company, phone,
                signature_text, signature_html, persona_context,
                warmup_enabled, daily_limit, ramp_schedule, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email,
            full_name,
            data.get("title", ""),
            data.get("company", "Intralog"),
            data.get("phone", ""),
            data.get("signature_text", ""),
            data.get("signature_html", ""),
            data.get("persona_context", ""),
            1 if data.get("warmup_enabled") else 0,
            data.get("daily_limit", 50),
            data.get("ramp_schedule", "conservative"),
            utc_now(),
            utc_now()
        ))
        conn.commit()
        conn.close()

        logger.info(f"Created new sender: {email}")
        return jsonify({"status": "success", "message": "Sender created"})
    except Exception as e:
        logger.error(f"Failed to create sender: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>", methods=["DELETE"])
def delete_sender(sender_email):
    """Delete a sender profile."""
    from lead_registry import get_connection
    from urllib.parse import unquote

    # URL decode the email parameter
    sender_email = unquote(sender_email)
    logger.info(f"Attempting to delete sender: {sender_email}")

    conn = get_connection()
    try:
        # Check if sender exists first
        existing = conn.execute("SELECT email FROM sender_signatures WHERE email = ?", (sender_email,)).fetchone()
        if not existing:
            conn.close()
            logger.warning(f"Sender not found: {sender_email}")
            return jsonify({"error": "Sender not found"}), 404

        # Delete the sender
        conn.execute("DELETE FROM sender_signatures WHERE email = ?", (sender_email,))
        conn.commit()
        conn.close()

        logger.info(f"Successfully deleted sender: {sender_email}")
        return jsonify({"status": "success", "message": "Sender deleted"})
    except Exception as e:
        logger.error(f"Failed to delete sender {sender_email}: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>/analytics")
def sender_analytics(sender_email):
    """Get analytics data for a specific sender."""
    from lead_registry import get_connection
    from urllib.parse import unquote

    sender_email = unquote(sender_email)
    logger.info(f"Fetching analytics for sender: {sender_email}")

    conn = get_connection()
    try:
        # Get email stats for this sender
        stats = conn.execute("""
            SELECT
                COUNT(CASE WHEN status != 'pending' THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'delivered' OR status = 'opened' OR status = 'replied' THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' OR status = 'replied' THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status = 'replied' THEN 1 END) as replied,
                COUNT(CASE WHEN status = 'bounced' THEN 1 END) as bounced,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed
            FROM emails
            WHERE sender_email = ?
        """, (sender_email,)).fetchone()

        # Get warmup status
        sender = conn.execute("""
            SELECT warmup_enabled, daily_limit, ramp_schedule, warmup_started_at, created_at
            FROM sender_signatures WHERE email = ?
        """, (sender_email,)).fetchone()

        conn.close()

        analytics = dict(stats) if stats else {
            "sent": 0, "delivered": 0, "opened": 0, "clicked": 0,
            "replied": 0, "bounced": 0, "unsubscribed": 0
        }

        # Calculate warmup day if enabled
        if sender and sender["warmup_enabled"]:
            from datetime import datetime
            # Use warmup_started_at if available, otherwise fall back to created_at
            start_date_str = sender["warmup_started_at"] or sender["created_at"]
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                warmup_day = (datetime.now(start_date.tzinfo) - start_date).days + 1
            else:
                warmup_day = 1
            analytics["warmup_day"] = min(max(warmup_day, 1), 14)  # Clamp between 1 and 14

            # Calculate current daily limit based on ramp schedule
            ramp_schedules = {
                "conservative": [5, 15, 25, 35, 50],  # 4 weeks
                "moderate": [10, 30, 50],  # 2 weeks
                "aggressive": [25, 50]  # 1 week
            }
            schedule = ramp_schedules.get(sender["ramp_schedule"], [50])
            week = min((warmup_day - 1) // 7, len(schedule) - 1)
            analytics["current_daily_limit"] = schedule[week]
        else:
            analytics["warmup_day"] = 0
            analytics["current_daily_limit"] = sender["daily_limit"] if sender else 50

        return jsonify(analytics)
    except Exception as e:
        logger.error(f"Failed to get sender analytics: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>/recipients")
def sender_recipients(sender_email):
    """Get recipients by category for drill-down view."""
    from lead_registry import get_connection
    from urllib.parse import unquote

    sender_email = unquote(sender_email)
    category = request.args.get("category", "sent")
    logger.info(f"Fetching {category} recipients for sender: {sender_email}")

    conn = get_connection()
    try:
        # Map category to status filter
        status_map = {
            "sent": ["sent", "delivered", "opened", "clicked", "replied"],
            "delivered": ["delivered", "opened", "clicked", "replied"],
            "opened": ["opened", "clicked", "replied"],
            "clicked": ["clicked"],
            "replied": ["replied"],
            "bounced": ["bounced"],
            "unsubscribed": ["unsubscribed"]
        }

        statuses = status_map.get(category, [category])
        placeholders = ",".join("?" * len(statuses))

        recipients = conn.execute(f"""
            SELECT
                e.recipient_email as email,
                l.first_name || ' ' || l.last_name as name,
                l.company_name as company,
                e.status,
                e.sent_at as timestamp
            FROM emails e
            LEFT JOIN leads l ON e.lead_id = l.id
            WHERE e.sender_email = ? AND e.status IN ({placeholders})
            ORDER BY e.sent_at DESC
            LIMIT 100
        """, (sender_email, *statuses)).fetchall()

        conn.close()

        return jsonify({
            "recipients": [dict(r) for r in recipients]
        })
    except Exception as e:
        logger.error(f"Failed to get sender recipients: {e}")
        conn.close()
        return jsonify({"error": str(e), "recipients": []}), 500


@app.route("/api/senders/<path:sender_email>/emails")
def sender_emails(sender_email):
    """Get all emails sent by a specific sender with full details."""
    from lead_registry import get_connection
    from urllib.parse import unquote

    sender_email = unquote(sender_email)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    status_filter = request.args.get("status", None)

    offset = (page - 1) * per_page

    logger.info(f"Fetching emails for sender: {sender_email}, page {page}")

    conn = get_connection()
    try:
        # Build query with optional status filter
        query = """
            SELECT
                e.id,
                e.recipient_email,
                e.subject,
                e.body_plain,
                e.status,
                e.sent_at,
                e.opened_at,
                e.clicked_at,
                e.replied_at,
                e.bounced_at,
                e.campaign_id,
                e.sequence_id,
                l.first_name,
                l.last_name,
                c.name as company_name
            FROM emails e
            LEFT JOIN leads_people l ON e.lead_id = l.person_key
            LEFT JOIN leads_company c ON l.company_key = c.company_key
            WHERE e.sender_email = ?
        """
        params = [sender_email]

        if status_filter:
            query += " AND e.status = ?"
            params.append(status_filter)

        query += " ORDER BY e.sent_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        emails = conn.execute(query, params).fetchall()

        # Get total count
        count_query = "SELECT COUNT(*) FROM emails WHERE sender_email = ?"
        count_params = [sender_email]
        if status_filter:
            count_query += " AND status = ?"
            count_params.append(status_filter)

        total = conn.execute(count_query, count_params).fetchone()[0]

        conn.close()

        return jsonify({
            "emails": [dict(e) for e in emails],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 0
        })
    except Exception as e:
        logger.error(f"Failed to get sender emails: {e}")
        conn.close()
        return jsonify({"error": str(e), "emails": [], "total": 0}), 500


@app.route("/api/signatures", methods=["GET"])
def get_signatures():
    """List all signatures."""
    from signature_manager import get_all_signatures

    signatures = get_all_signatures()
    return jsonify({"signatures": signatures})


@app.route("/api/signatures/import", methods=["POST"])
def import_signatures():
    """Import signatures from Outlook."""
    from signature_manager import import_outlook_signatures

    try:
        imported_ids = import_outlook_signatures()
        return jsonify({
            "status": "success",
            "count": len(imported_ids),
            "signature_ids": imported_ids
        })
    except Exception as e:
        logger.error(f"Signature import failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/signatures/<signature_id>", methods=["GET"])
def get_signature(signature_id):
    """Get signature by ID."""
    from signature_manager import get_signature

    signature = get_signature(signature_id)
    if signature:
        return jsonify(signature)
    else:
        return jsonify({"error": "Signature not found"}), 404


@app.route("/api/signatures/<signature_id>", methods=["PUT"])
def update_signature(signature_id):
    """Update signature."""
    from signature_manager import update_signature

    data = request.json
    try:
        update_signature(
            signature_id,
            name=data.get("name"),
            html_content=data.get("html_content"),
            plain_text_content=data.get("plain_text_content"),
            is_default=data.get("is_default")
        )
        return jsonify({"status": "updated"})
    except Exception as e:
        logger.error(f"Signature update failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/signatures/<signature_id>", methods=["DELETE"])
def delete_signature(signature_id):
    """Delete signature."""
    from signature_manager import delete_signature

    try:
        delete_signature(signature_id)
        return jsonify({"status": "deleted"})
    except Exception as e:
        logger.error(f"Signature deletion failed: {e}")
        return jsonify({"error": str(e)}), 500


# ====================
# NEW ENDPOINTS: Sequence Management
# ====================

@app.route("/api/campaigns/<campaign_id>/sequence", methods=["GET"])
def get_campaign_sequence(campaign_id):
    """Load sequence for a campaign."""
    from sequence_engine import load_sequence_by_campaign

    sequence = load_sequence_by_campaign(campaign_id)
    if sequence:
        return jsonify(sequence)
    else:
        return jsonify({"steps": []})


@app.route("/api/campaigns/<campaign_id>/sequence", methods=["PUT"])
def save_campaign_sequence(campaign_id):
    """Save sequence for a campaign."""
    from sequence_engine import create_sequence, load_sequence_by_campaign

    data = request.json
    steps = data.get("steps", [])
    name = data.get("name", f"Sequence for {campaign_id}")
    sender_email = data.get("sender_email", "")

    try:
        # Check if sequence exists
        existing = load_sequence_by_campaign(campaign_id)

        if existing:
            # Update existing sequence
            from lead_registry import get_connection, utc_now
            conn = get_connection()
            conn.execute("""
                UPDATE sequences
                SET steps = ?, name = ?, sender_email = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(steps), name, sender_email, utc_now(), existing['id']))
            conn.close()
            sequence_id = existing['id']
        else:
            # Create new sequence with sender_email
            sequence_id = create_sequence(campaign_id, name, steps, sender_email=sender_email)

        return jsonify({"status": "saved", "sequence_id": sequence_id})
    except Exception as e:
        logger.error(f"Sequence save failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/campaigns/<campaign_id>/sequence/enroll", methods=["POST"])
def enroll_leads_in_sequence(campaign_id):
    """Enroll leads in a campaign sequence."""
    from sequence_engine import load_sequence_by_campaign, enroll_lead_in_sequence

    data = request.json
    person_keys = data.get("person_keys", [])

    sequence = load_sequence_by_campaign(campaign_id)
    if not sequence:
        return jsonify({"error": "No sequence found for this campaign"}), 404

    enrolled_count = 0
    errors = []

    for person_key in person_keys:
        try:
            enroll_lead_in_sequence(person_key, campaign_id, sequence['id'])
            enrolled_count += 1
        except Exception as e:
            errors.append(f"{person_key}: {str(e)}")

    return jsonify({
        "enrolled": enrolled_count,
        "total": len(person_keys),
        "errors": errors
    })


@app.route("/api/campaigns/<campaign_id>/sequence/status", methods=["GET"])
def get_sequence_status(campaign_id):
    """Get sequence execution status."""
    from sequence_engine import load_sequence_by_campaign, get_sequence_status as get_status

    sequence = load_sequence_by_campaign(campaign_id)
    if not sequence:
        return jsonify({"error": "No sequence found"}), 404

    status = get_status(sequence['id'])
    return jsonify({"status": status})


# ====================
# NEW ENDPOINTS: Email Preview & Test
# ====================

@app.route("/api/campaigns/<campaign_id>/preview", methods=["POST"])
def preview_campaign_email(campaign_id):
    """Generate email preview for a specific lead."""
    data = request.json
    person_key = data.get("person_key")

    if not person_key:
        return jsonify({"error": "person_key required"}), 400

    # Load person and company data
    person = get_person_by_key(person_key)
    if not person:
        return jsonify({"error": "Person not found"}), 404

    company = get_company_by_key(person['company_key']) if person.get('company_key') else {}

    # Load campaign
    campaigns_data = load_json()
    campaigns = {c['id']: c for c in campaigns_data.get('campaigns', [])}
    campaign = campaigns.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    # Get personalization mode from campaign settings
    settings = campaign.get('settings', {})
    personalization_mode = settings.get('personalization_mode', 'signal_based')

    # Generate personalized content
    from personalization_engine import generate_email_by_mode

    lead_data = {
        'Company': company.get('name', ''),
        'company_name': company.get('name', ''),
        'first_name': person.get('first_name', ''),
        'First Name': person.get('first_name', ''),
        'title': person.get('title', ''),
        'Job title': person.get('title', '')
    }

    apollo_data = {
        'industry': company.get('industry', ''),
        'employee_count': company.get('employee_count', ''),
        'technologies': company.get('technologies', ''),
        'wms_system': company.get('wms_system', ''),
        'equipment_signals': company.get('equipment_signals', ''),
        'job_postings_relevant': company.get('job_postings_relevant', 0)
    }

    template_context = {
        'strategy': campaign.get('strategy', 'conventional'),
        'pain_theme': 'throughput'
    }

    personalization, success = generate_email_by_mode(
        personalization_mode,
        lead_data,
        apollo_data,
        template_context
    )

    if not success:
        personalization = "[Personalization generation failed]"

    # Build email content
    sequence = campaign.get('sequence', {})
    email_template = sequence.get('email_1', {}).get('variant_a', {})

    subject = email_template.get('subject', 'Subject line here')
    body_template = email_template.get('body', '')

    # Replace variables
    body_html = body_template.replace('{{personalization_sentence}}', personalization)
    body_html = body_html.replace('{{first_name}}', person.get('first_name', ''))
    body_html = body_html.replace('{{company_name}}', company.get('name', ''))

    # Get signature
    from signature_manager import get_default_signature
    signature = get_default_signature()
    if signature:
        body_html += f"\n\n{signature['html_content']}"

    # Get sender
    sender_profile = Config.get_sender_profile(0)

    return jsonify({
        "subject": subject,
        "body_html": body_html,
        "body_plain": html_to_plain_text(body_html),
        "sender_name": sender_profile['full_name'],
        "sender_email": sender_profile['email'],
        "recipient_name": f"{person['first_name']} {person['last_name']}",
        "recipient_email": person['email']
    })


@app.route("/api/campaigns/<campaign_id>/test-email", methods=["POST"])
def send_test_email(campaign_id):
    """Send test email to specified address."""
    data = request.json
    person_key = data.get("person_key")
    test_recipient = data.get("test_recipient")

    if not person_key or not test_recipient:
        return jsonify({"error": "person_key and test_recipient required"}), 400

    # Load person and company data
    person = get_person_by_key(person_key)
    if not person:
        return jsonify({"error": "Person not found"}), 404

    company = get_company_by_key(person['company_key']) if person.get('company_key') else {}

    # Load campaign
    campaigns_data = load_json()
    campaigns = {c['id']: c for c in campaigns_data.get('campaigns', [])}
    campaign = campaigns.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    # Get personalization mode from campaign settings
    settings = campaign.get('settings', {})
    personalization_mode = settings.get('personalization_mode', 'signal_based')

    # Generate personalized content
    from personalization_engine import generate_email_by_mode

    lead_data = {
        'Company': company.get('name', ''),
        'company_name': company.get('name', ''),
        'first_name': person.get('first_name', ''),
        'First Name': person.get('first_name', ''),
        'title': person.get('title', ''),
        'Job title': person.get('title', '')
    }

    apollo_data = {
        'industry': company.get('industry', ''),
        'employee_count': company.get('employee_count', ''),
        'technologies': company.get('technologies', ''),
        'wms_system': company.get('wms_system', ''),
        'equipment_signals': company.get('equipment_signals', ''),
        'job_postings_relevant': company.get('job_postings_relevant', 0)
    }

    template_context = {
        'strategy': campaign.get('strategy', 'conventional'),
        'pain_theme': 'throughput'
    }

    personalization, success = generate_email_by_mode(
        personalization_mode,
        lead_data,
        apollo_data,
        template_context
    )

    if not success:
        personalization = "[Personalization generation failed]"

    # Build email content
    sequence = campaign.get('sequence', {})
    email_template = sequence.get('email_1', {}).get('variant_a', {})

    subject = email_template.get('subject', 'Subject line here')
    body_template = email_template.get('body', '')

    # Replace variables
    body_html = body_template.replace('{{personalization_sentence}}', personalization)
    body_html = body_html.replace('{{first_name}}', person.get('first_name', ''))
    body_html = body_html.replace('{{company_name}}', company.get('name', ''))

    # Get signature
    from signature_manager import get_default_signature
    signature = get_default_signature()
    if signature:
        body_html += f"\n\n{signature['html_content']}"

    # Get sender
    sender_profile = Config.get_sender_profile(0)

    # Send via SendGrid
    try:
        success = send_via_sendgrid(
            to_email=test_recipient,
            from_email=sender_profile['email'],
            from_name=sender_profile['full_name'],
            subject=f"[TEST] {subject}",
            html_body=body_html,
            plain_body=html_to_plain_text(body_html)
        )

        if success:
            logger.info(f"Test email sent successfully to {test_recipient}")
            return jsonify({"status": "sent", "message": f"Test email sent to {test_recipient}"})
        else:
            logger.error("SendGrid API failed to send test email")
            return jsonify({"error": "Failed to send email via SendGrid"}), 500
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        return jsonify({"error": str(e)}), 500


# ====================
# NEW ENDPOINTS: Variables & Webhooks
# ====================

@app.route("/api/variables", methods=["GET"])
def get_available_variables():
    """Return all available template variables."""
    variables = [
        # Person fields
        {"name": "first_name", "category": "Person", "example": "John"},
        {"name": "last_name", "category": "Person", "example": "Smith"},
        {"name": "title", "category": "Person", "example": "VP Operations"},
        {"name": "email", "category": "Person", "example": "john@company.com"},
        {"name": "phone", "category": "Person", "example": "+1-801-555-0100"},
        {"name": "linkedin_url", "category": "Person", "example": "linkedin.com/in/johnsmith"},
        {"name": "seniority", "category": "Person", "example": "Director"},
        {"name": "department", "category": "Person", "example": "Operations"},

        # Company fields
        {"name": "company_name", "category": "Company", "example": "Acme Logistics"},
        {"name": "industry", "category": "Company", "example": "3PL"},
        {"name": "employee_count", "category": "Company", "example": "350"},
        {"name": "estimated_revenue", "category": "Company", "example": "$50M-$100M"},
        {"name": "technologies", "category": "Company", "example": "Manhattan WMS, SAP"},
        {"name": "wms_system", "category": "Company", "example": "Manhattan"},
        {"name": "city", "category": "Company", "example": "Salt Lake City"},
        {"name": "state", "category": "Company", "example": "Utah"},

        # Enrichment/Signals
        {"name": "job_postings_count", "category": "Signals", "example": "5"},
        {"name": "job_postings_relevant", "category": "Signals", "example": "3"},
        {"name": "equipment_signals", "category": "Signals", "example": "conveyor, sortation"},
        {"name": "intent_score", "category": "Signals", "example": "0.75"},

        # Personalization
        {"name": "personalization_sentence", "category": "AI Generated", "example": "Your recent expansion..."},
        {"name": "pain_statement", "category": "AI Generated", "example": "Labor costs cutting into margins"},
        {"name": "credibility_anchor", "category": "AI Generated", "example": "We helped a 200k sq ft 3PL..."},

        # Sender
        {"name": "sender_name", "category": "Sender", "example": "Aaron Cendejas"},
        {"name": "sender_email", "category": "Sender", "example": "aaron@intralog.io"},
        {"name": "sender_title", "category": "Sender", "example": "Senior Systems Engineer"},
        {"name": "signature", "category": "Sender", "example": "[HTML signature]"}
    ]

    return jsonify({"variables": variables})


@app.route("/api/webhooks/bland-ai", methods=["POST"])
def bland_ai_webhook():
    """Handle Bland.ai call completion webhooks."""
    data = request.json

    call_id = data.get("call_id")
    status = data.get("status")  # 'completed', 'failed', 'no-answer'
    duration = data.get("call_length")  # seconds
    transcript = data.get("transcript")
    recording_url = data.get("recording_url")

    logger.info(f"Bland.ai webhook received: call_id={call_id}, status={status}, duration={duration}s")

    # Update outreach_log with call outcome
    from lead_registry import get_connection
    conn = get_connection()

    try:
        conn.execute("""
            UPDATE outreach_log
            SET status = ?,
                action_metadata = json_set(
                    action_metadata,
                    '$.call_duration', ?,
                    '$.transcript', ?,
                    '$.recording_url', ?
                )
            WHERE json_extract(action_metadata, '$.call_id') = ?
        """, (status, duration, transcript, recording_url, call_id))

        conn.close()

        return jsonify({"status": "received"})
    except Exception as e:
        logger.error(f"Failed to update call status: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


# ====================
# NEW ENDPOINTS: Apollo Credit Tracking
# ====================

@app.route("/api/apollo/credits", methods=["GET"])
def get_apollo_credits():
    """Track Apollo credit usage."""
    from lead_registry import get_connection

    conn = get_connection()

    try:
        credits_used = conn.execute("""
            SELECT
                COUNT(*) as total_enrichments,
                SUM(reveal_phone_number) as phone_reveals,
                SUM(reveal_personal_emails) as email_reveals
            FROM apollo_queue
            WHERE status = 'enriched'
        """).fetchone()

        conn.close()

        total = credits_used['total_enrichments'] if credits_used else 0
        phones = credits_used['phone_reveals'] if credits_used else 0
        emails = credits_used['email_reveals'] if credits_used else 0

        return jsonify({
            "credits_used": total,
            "phone_reveals": phones,
            "email_reveals": emails,
            "credits_remaining": 100 - total,
            "breakdown": {
                "phone_numbers": phones,
                "personal_emails": emails
            }
        })
    except Exception as e:
        logger.error(f"Failed to get credit usage: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


# ====================
# NEW ENDPOINTS: Sequence Templates
# ====================

@app.route("/api/sequence-templates", methods=["GET"])
def list_sequence_templates():
    """List all sequence templates (system + user-created)."""
    from lead_registry import get_connection

    conn = get_connection()

    try:
        templates = conn.execute("""
            SELECT * FROM sequence_templates
            ORDER BY is_system_template DESC, created_at DESC
        """).fetchall()

        conn.close()

        return jsonify({
            "templates": [dict(t) for t in templates]
        })
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        conn.close()
        return jsonify({"error": str(e), "templates": []}), 500


@app.route("/api/sequence-templates/<template_id>", methods=["GET"])
def get_sequence_template(template_id):
    """Get specific sequence template."""
    from lead_registry import get_connection

    conn = get_connection()

    try:
        template = conn.execute("""
            SELECT * FROM sequence_templates WHERE id = ?
        """, (template_id,)).fetchone()

        conn.close()

        if not template:
            return jsonify({"error": "Template not found"}), 404

        return jsonify(dict(template))
    except Exception as e:
        logger.error(f"Failed to get template: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/sequence-templates", methods=["POST"])
def save_sequence_template():
    """Save current sequence as template."""
    from lead_registry import get_connection, utc_now
    import uuid

    data = request.json
    name = data.get("name")
    description = data.get("description", "")
    category = data.get("category", "custom")
    steps = data.get("steps", [])

    if not name or not steps:
        return jsonify({"error": "name and steps required"}), 400

    conn = get_connection()

    try:
        template_id = f"template_{uuid.uuid4().hex[:12]}"
        now = utc_now()

        conn.execute("""
            INSERT INTO sequence_templates
            (id, name, description, category, steps, is_system_template, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """, (template_id, name, description, category, json.dumps(steps), now, now))

        conn.commit()
        conn.close()

        logger.info(f"Saved template: {template_id}")
        return jsonify({"template_id": template_id, "message": "Template saved"})
    except Exception as e:
        logger.error(f"Failed to save template: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/sequence-templates/<template_id>/clone", methods=["POST"])
def clone_sequence_template(template_id):
    """Clone template to new sequence for campaign."""
    from lead_registry import get_connection

    data = request.json
    campaign_id = data.get("campaign_id")

    if not campaign_id:
        return jsonify({"error": "campaign_id required"}), 400

    conn = get_connection()

    try:
        # Get template
        template = conn.execute("""
            SELECT * FROM sequence_templates WHERE id = ?
        """, (template_id,)).fetchone()

        if not template:
            conn.close()
            return jsonify({"error": "Template not found"}), 404

        # Create sequence from template
        sequence_id = f"seq_{campaign_id}_{uuid.uuid4().hex[:8]}"
        now = utc_now()

        conn.execute("""
            INSERT OR REPLACE INTO sequences
            (id, campaign_id, name, steps, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sequence_id, campaign_id, template['name'], template['steps'], now, now))

        conn.commit()
        conn.close()

        logger.info(f"Cloned template {template_id} to sequence {sequence_id}")
        return jsonify({
            "sequence_id": sequence_id,
            "message": "Template cloned to sequence"
        })
    except Exception as e:
        logger.error(f"Failed to clone template: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


# ====================
# NEW ENDPOINTS: Unified Inbox
# ====================

@app.route("/api/inbox", methods=["GET"])
def get_inbox_activity():
    """Get unified activity feed across all channels."""
    from lead_registry import get_connection

    campaign_id = request.args.get("campaign_id")
    channel = request.args.get("channel", "all")
    status = request.args.get("status", "all")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    conn = get_connection()

    try:
        query = """
            SELECT
                ol.id,
                ol.campaign_id,
                ol.person_key,
                ol.status,
                ol.sent_at as timestamp,
                ol.channel,
                ol.sequence_step,
                ol.action_metadata,
                lp.first_name,
                lp.last_name,
                lp.email as recipient_email,
                lp.company_key,
                lc.name as company_name
            FROM outreach_log ol
            LEFT JOIN leads_people lp ON ol.person_key = lp.person_key
            LEFT JOIN leads_company lc ON lp.company_key = lc.company_key
            WHERE 1=1
        """

        params = []

        if campaign_id:
            query += " AND ol.campaign_id = ?"
            params.append(campaign_id)

        if channel != "all":
            query += " AND ol.channel = ?"
            params.append(channel)

        if status != "all":
            query += " AND ol.status = ?"
            params.append(status)

        query += " ORDER BY ol.sent_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        activities = conn.execute(query, params).fetchall()
        conn.close()

        # Format activities
        formatted = []
        for activity in activities:
            act_dict = dict(activity)

            # Parse action_metadata if it exists
            if act_dict.get('action_metadata'):
                try:
                    act_dict['metadata'] = json.loads(act_dict['action_metadata'])
                except:
                    act_dict['metadata'] = {}

            # Add recipient name
            act_dict['recipient_name'] = f"{act_dict.get('first_name', '')} {act_dict.get('last_name', '')}".strip()

            # Add preview based on channel
            if act_dict.get('metadata'):
                if act_dict['channel'] == 'email':
                    act_dict['subject'] = act_dict['metadata'].get('subject', '')
                    act_dict['preview'] = act_dict['metadata'].get('preview', '')[:100]
                elif act_dict['channel'] == 'call':
                    act_dict['duration'] = act_dict['metadata'].get('duration', '0:00')
                elif act_dict['channel'] == 'linkedin':
                    act_dict['linkedin_type'] = act_dict['metadata'].get('type', 'message')

            formatted.append(act_dict)

        return jsonify({"activities": formatted})
    except Exception as e:
        logger.error(f"Failed to get inbox: {e}")
        conn.close()
        return jsonify({"error": str(e), "activities": []}), 500


@app.route("/api/inbox/<activity_id>", methods=["GET"])
def get_activity_details(activity_id):
    """Get full details for specific activity."""
    from lead_registry import get_connection

    conn = get_connection()

    try:
        activity = conn.execute("""
            SELECT
                ol.*,
                lp.first_name,
                lp.last_name,
                lp.email as recipient_email,
                lc.name as company_name,
                s.name as sequence_name
            FROM outreach_log ol
            LEFT JOIN leads_people lp ON ol.person_key = lp.person_key
            LEFT JOIN leads_company lc ON lp.company_key = lc.company_key
            LEFT JOIN sequences s ON ol.campaign_id = s.campaign_id
            WHERE ol.id = ?
        """, (activity_id,)).fetchone()

        conn.close()

        if not activity:
            return jsonify({"error": "Activity not found"}), 404

        act_dict = dict(activity)

        # Parse metadata
        details = {}
        if act_dict.get('action_metadata'):
            try:
                metadata = json.loads(act_dict['action_metadata'])
                details = metadata
            except:
                pass

        # Add sender info
        sender_profile = Config.get_sender_profile(0)
        details['sender_email'] = sender_profile['email']
        details['sender_name'] = sender_profile['full_name']
        details['sequence_name'] = act_dict.get('sequence_name', '')

        return jsonify({
            "id": act_dict['id'],
            "channel": act_dict['channel'],
            "status": act_dict['status'],
            "timestamp": act_dict['sent_at'],
            "recipient_name": f"{act_dict.get('first_name', '')} {act_dict.get('last_name', '')}".strip(),
            "recipient_email": act_dict.get('recipient_email', ''),
            "company_name": act_dict.get('company_name', ''),
            "details": details
        })
    except Exception as e:
        logger.error(f"Failed to get activity details: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>/signature", methods=["PUT"])
def update_sender_signature(sender_email):
    """Update sender profile including signature, persona, and warmup settings."""
    from lead_registry import get_connection, utc_now
    from urllib.parse import unquote

    sender_email = unquote(sender_email)
    data = request.json
    signature_text = data.get("signature_text", "")
    signature_html = data.get("signature_html", "")
    persona_context = data.get("persona_context", "")
    warmup_enabled = 1 if data.get("warmup_enabled") else 0
    daily_limit = data.get("daily_limit", 50)
    ramp_schedule = data.get("ramp_schedule", "conservative")

    logger.info(f"Updating sender profile: {sender_email}")

    conn = get_connection()
    try:
        # Check if warmup is being newly enabled (to set warmup_started_at)
        existing = conn.execute("""
            SELECT warmup_enabled, warmup_started_at FROM sender_signatures WHERE email = ?
        """, (sender_email,)).fetchone()

        # Determine warmup_started_at value
        warmup_started_at = None
        if warmup_enabled:
            if existing and existing["warmup_started_at"]:
                # Keep existing start date
                warmup_started_at = existing["warmup_started_at"]
            elif not existing or not existing["warmup_enabled"]:
                # Warmup is being newly enabled - set start date to now
                warmup_started_at = utc_now()
                logger.info(f"Warmup newly enabled for {sender_email}, starting at {warmup_started_at}")

        # Update sender with all fields including signature_text and warmup settings
        conn.execute("""
            INSERT INTO sender_signatures (
                email, full_name, title, company, phone,
                signature_text, signature_html, persona_context,
                warmup_enabled, daily_limit, ramp_schedule, warmup_started_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                full_name = excluded.full_name,
                title = excluded.title,
                company = excluded.company,
                phone = excluded.phone,
                signature_text = excluded.signature_text,
                signature_html = excluded.signature_html,
                persona_context = excluded.persona_context,
                warmup_enabled = excluded.warmup_enabled,
                daily_limit = excluded.daily_limit,
                ramp_schedule = excluded.ramp_schedule,
                warmup_started_at = COALESCE(excluded.warmup_started_at, sender_signatures.warmup_started_at),
                updated_at = excluded.updated_at
        """, (
            sender_email,
            data.get("full_name", ""),
            data.get("title", ""),
            data.get("company", "Intralog"),
            data.get("phone", ""),
            signature_text,
            signature_html,
            persona_context,
            warmup_enabled,
            daily_limit,
            ramp_schedule,
            warmup_started_at,
            utc_now()
        ))
        conn.commit()
        conn.close()

        logger.info(f"Successfully updated sender: {sender_email}")
        return jsonify({"status": "success", "message": "Sender updated"})
    except Exception as e:
        logger.error(f"Failed to update sender {sender_email}: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>/warmup", methods=["GET"])
def get_warmup_status(sender_email):
    """Get warmup status for a sender."""
    from warmup_controller import WarmupController

    try:
        controller = WarmupController()
        status = controller.get_warmup_status(sender_email)

        if not status:
            return jsonify({"error": "Sender not found"}), 404

        return jsonify(status)
    except Exception as e:
        logger.error(f"Failed to get warmup status for {sender_email}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>/warmup", methods=["POST"])
def enable_warmup(sender_email):
    """Enable warmup for a sender."""
    from warmup_controller import WarmupController

    data = request.json
    ramp_schedule = data.get("ramp_schedule", "conservative")
    warmup_service = data.get("warmup_service")
    warmup_service_id = data.get("warmup_service_id")

    try:
        controller = WarmupController()
        success = controller.enable_warmup(
            sender_email,
            ramp_schedule=ramp_schedule,
            warmup_service=warmup_service,
            warmup_service_id=warmup_service_id
        )

        if success:
            return jsonify({
                "status": "success",
                "message": f"Warmup enabled for {sender_email}",
                "ramp_schedule": ramp_schedule
            })
        else:
            return jsonify({"error": "Failed to enable warmup"}), 400

    except Exception as e:
        logger.error(f"Failed to enable warmup for {sender_email}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/senders/<path:sender_email>/warmup", methods=["DELETE"])
def disable_warmup(sender_email):
    """Disable warmup for a sender."""
    from warmup_controller import WarmupController

    try:
        controller = WarmupController()
        success = controller.disable_warmup(sender_email)

        if success:
            return jsonify({
                "status": "success",
                "message": f"Warmup disabled for {sender_email}"
            })
        else:
            return jsonify({"error": "Failed to disable warmup"}), 400

    except Exception as e:
        logger.error(f"Failed to disable warmup for {sender_email}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/warmup/status", methods=["GET"])
def get_all_warmup_status():
    """Get warmup status for all senders with warmup enabled."""
    from warmup_controller import WarmupController

    try:
        controller = WarmupController()
        statuses = controller.get_all_warmup_senders()

        return jsonify({
            "senders": statuses,
            "total": len(statuses)
        })
    except Exception as e:
        logger.error(f"Failed to get warmup statuses: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sequences/<sequence_id>/settings", methods=["GET"])
def get_sequence_settings(sequence_id):
    """Get sequence settings (personalization mode, signature toggle)."""
    from lead_registry import get_connection

    conn = get_connection()
    try:
        settings = conn.execute("""
            SELECT * FROM sequence_settings WHERE sequence_id = ?
        """, (sequence_id,)).fetchone()

        conn.close()

        if settings:
            return jsonify(dict(settings))
        else:
            # Return defaults
            return jsonify({
                "sequence_id": sequence_id,
                "personalization_mode": "signal_based",
                "include_signature": 1
            })
    except Exception as e:
        logger.error(f"Failed to get sequence settings: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/sequences/<sequence_id>/settings", methods=["PUT"])
def update_sequence_settings(sequence_id):
    """Update sequence settings."""
    from lead_registry import get_connection

    data = request.json
    personalization_mode = data.get("personalization_mode", "signal_based")
    include_signature = data.get("include_signature", 1)

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO sequence_settings (sequence_id, personalization_mode, include_signature)
            VALUES (?, ?, ?)
            ON CONFLICT(sequence_id) DO UPDATE SET
                personalization_mode = excluded.personalization_mode,
                include_signature = excluded.include_signature
        """, (sequence_id, personalization_mode, include_signature))
        conn.commit()
        conn.close()

        logger.info(f"Updated settings for sequence {sequence_id}")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Failed to update sequence settings: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


# ====================
# WEBSITE VISITOR TRACKING ENDPOINTS
# ====================

# 1x1 transparent GIF for tracking pixel
TRACKING_PIXEL = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'


@app.route("/api/track/pixel.gif", methods=["GET", "OPTIONS"])
def tracking_pixel():
    """1x1 transparent GIF tracking pixel for external websites."""
    from flask import Response, make_response
    from visitor_tracking import record_visit

    if request.method == "OPTIONS":
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        return response

    # Get visitor info from request
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip_address and "," in ip_address:
        ip_address = ip_address.split(",")[0].strip()

    page_url = request.args.get("url", "")
    referrer = request.args.get("ref", request.headers.get("Referer", ""))
    user_agent = request.headers.get("User-Agent", "")
    session_id = request.args.get("sid", None)

    # Record the visit asynchronously (non-blocking)
    try:
        record_visit(
            ip_address=ip_address,
            page_url=page_url,
            referrer=referrer,
            user_agent=user_agent,
            session_id=session_id
        )
    except Exception as e:
        logger.error(f"Failed to record visit: {e}")

    # Return tracking pixel
    response = Response(TRACKING_PIXEL, mimetype="image/gif")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/api/track/script.js", methods=["GET"])
def tracking_script():
    """JavaScript tracking snippet for external websites."""
    from flask import Response

    backend_url = Config.BASE_URL

    script = f'''
(function() {{
    var _vt = window._vt || [];
    var sessionId = localStorage.getItem('_vt_sid');
    if (!sessionId) {{
        sessionId = 'sid_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
        localStorage.setItem('_vt_sid', sessionId);
    }}

    function trackPageView() {{
        var img = new Image();
        var params = [
            'url=' + encodeURIComponent(window.location.href),
            'ref=' + encodeURIComponent(document.referrer || ''),
            'sid=' + encodeURIComponent(sessionId),
            't=' + Date.now()
        ];
        img.src = '{backend_url}/api/track/pixel.gif?' + params.join('&');
    }}

    // Track initial page view
    if (document.readyState === 'complete') {{
        trackPageView();
    }} else {{
        window.addEventListener('load', trackPageView);
    }}

    // Track SPA navigation (pushState)
    var originalPushState = history.pushState;
    history.pushState = function() {{
        originalPushState.apply(history, arguments);
        setTimeout(trackPageView, 100);
    }};

    window.addEventListener('popstate', function() {{
        setTimeout(trackPageView, 100);
    }});

    window._vt = {{ track: trackPageView, sessionId: sessionId }};
}})();
'''

    response = Response(script, mimetype="application/javascript")
    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/api/track/visit", methods=["POST", "OPTIONS"])
def track_visit():
    """Record a visitor event from the tracking script."""
    from visitor_tracking import record_visit

    if request.method == "OPTIONS":
        return "", 204

    data = request.json or {}

    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip_address and "," in ip_address:
        ip_address = ip_address.split(",")[0].strip()

    result = record_visit(
        ip_address=ip_address,
        page_url=data.get("url", ""),
        referrer=data.get("referrer", ""),
        user_agent=request.headers.get("User-Agent", ""),
        session_id=data.get("session_id")
    )

    if result.get("success"):
        return "", 204
    else:
        return jsonify(result), 429 if result.get("error") == "rate_limited" else 500


@app.route("/api/visitors", methods=["GET"])
def list_visitors():
    """List identified visitor companies with filtering."""
    from visitor_reconciliation import get_visitor_companies

    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    source = request.args.get("source")
    min_visits = request.args.get("min_visits")
    days = request.args.get("days")
    enriched_only = request.args.get("enriched") == "true"

    result = get_visitor_companies(
        limit=limit,
        offset=offset,
        source=source,
        min_visits=int(min_visits) if min_visits else None,
        days=int(days) if days else None,
        enriched_only=enriched_only
    )

    return jsonify(result)


@app.route("/api/visitors/<company_key>", methods=["GET"])
def visitor_detail(company_key):
    """Get detailed visitor company info with visit history."""
    from visitor_reconciliation import get_visitor_company_detail

    detail = get_visitor_company_detail(company_key)

    if not detail:
        return jsonify({"error": "Visitor company not found"}), 404

    return jsonify(detail)


@app.route("/api/visitors/analytics", methods=["GET"])
def visitor_analytics():
    """Aggregated visitor analytics."""
    from visitor_tracking import get_visitor_stats
    from visitor_reconciliation import get_reconciliation_stats

    tracking_stats = get_visitor_stats()
    reconciliation_stats = get_reconciliation_stats()

    return jsonify({
        "tracking": tracking_stats,
        "reconciliation": reconciliation_stats
    })


@app.route("/api/visitors/<company_key>/find-contacts", methods=["POST"])
def visitor_find_contacts(company_key):
    """Trigger Apollo enrichment for a visitor company."""
    from visitor_reconciliation import get_visitor_company_detail
    from lead_registry import get_connection

    detail = get_visitor_company_detail(company_key)
    if not detail:
        return jsonify({"error": "Visitor company not found"}), 404

    domain = detail.get("domain")
    if not domain:
        return jsonify({"error": "No domain available for company"}), 400

    # TODO: Implement Apollo company search by domain
    # For now, mark as enrichment requested
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE visitor_companies SET apollo_enriched = 1, updated_at = ?
            WHERE company_key = ?
        """, (utc_now(), company_key))
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "status": "queued",
        "message": f"Enrichment queued for domain: {domain}",
        "company_key": company_key
    })


@app.route("/api/integrations/leadfeeder/status", methods=["GET"])
def leadfeeder_status():
    """Check Leadfeeder integration status."""
    from leadfeeder_scraper import get_leadfeeder_status

    status = get_leadfeeder_status()
    return jsonify(status)


@app.route("/api/integrations/leadfeeder/sync", methods=["POST"])
def leadfeeder_manual_sync():
    """Manually trigger Leadfeeder scrape."""
    from leadfeeder_scraper import scrape_leadfeeder

    result = scrape_leadfeeder()
    return jsonify(result)


@app.route("/api/integrations/leadfeeder/screenshots", methods=["GET"])
def leadfeeder_screenshots():
    """Get list of Leadfeeder scrape screenshots."""
    import os
    import glob

    screenshot_dir = "/tmp/leadfeeder_screenshots"
    if not os.path.exists(screenshot_dir):
        return jsonify({"screenshots": []})

    # Get all PNG files, sorted by modification time (newest first)
    screenshots = glob.glob(f"{screenshot_dir}/*.png")
    screenshots.sort(key=os.path.getmtime, reverse=True)

    # Return only the 10 most recent screenshots with their metadata
    results = []
    for filepath in screenshots[:10]:
        filename = os.path.basename(filepath)
        mtime = os.path.getmtime(filepath)
        results.append({
            "filename": filename,
            "timestamp": mtime,
            "url": f"/api/integrations/leadfeeder/screenshots/{filename}"
        })

    return jsonify({"screenshots": results})


@app.route("/api/integrations/leadfeeder/screenshots/<filename>", methods=["GET"])
def leadfeeder_screenshot_file(filename):
    """Serve a specific screenshot file."""
    import os
    from flask import send_file

    screenshot_dir = "/tmp/leadfeeder_screenshots"
    filepath = os.path.join(screenshot_dir, filename)

    # Security: ensure the file is within the screenshot directory
    if not os.path.abspath(filepath).startswith(os.path.abspath(screenshot_dir)):
        return jsonify({"error": "Invalid filename"}), 400

    if not os.path.exists(filepath):
        return jsonify({"error": "Screenshot not found"}), 404

    return send_file(filepath, mimetype='image/png')


@app.route("/api/integrations/leadfeeder/vnc/status", methods=["GET"])
def leadfeeder_vnc_status():
    """Get VNC server status."""
    try:
        from vnc_manager import get_vnc_manager
        vnc = get_vnc_manager()
        return jsonify({
            "running": vnc.is_running(),
            "websocket_port": vnc.websocket_port if vnc.is_running() else None,
            "display": vnc.display if vnc.is_running() else None
        })
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})


@sock.route('/vnc-websocket')
def vnc_websocket(ws):
    """WebSocket proxy to VNC server."""
    import socket
    import select

    logger.info("VNC WebSocket connection initiated")

    try:
        # Connect to websockify server on localhost:6080
        vnc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        vnc_socket.connect(('localhost', 6080))
        vnc_socket.setblocking(False)

        logger.info("Connected to websockify server")

        # Proxy data between WebSocket and VNC socket
        while True:
            # Check if either socket has data
            readable, _, exceptional = select.select([vnc_socket], [], [vnc_socket], 0.1)

            # Forward data from VNC to WebSocket
            if vnc_socket in readable:
                try:
                    data = vnc_socket.recv(4096)
                    if not data:
                        break
                    ws.send(data)
                except Exception as e:
                    logger.error(f"Error receiving from VNC: {e}")
                    break

            # Forward data from WebSocket to VNC
            try:
                data = ws.receive(timeout=0.1)
                if data is None:
                    continue
                if isinstance(data, str):
                    data = data.encode('utf-8')
                vnc_socket.sendall(data)
            except Exception as e:
                if "timed out" not in str(e):
                    logger.error(f"Error receiving from WebSocket: {e}")
                    break

            # Check for exceptions
            if vnc_socket in exceptional:
                break

    except Exception as e:
        logger.error(f"VNC WebSocket proxy error: {e}")
    finally:
        try:
            vnc_socket.close()
        except:
            pass
        logger.info("VNC WebSocket connection closed")


@app.route("/vnc-viewer")
def vnc_viewer():
    """Serve simple VNC viewer page."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Leadfeeder Scraper - Live View</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            background: #1a1a1a;
            font-family: system-ui, -apple-system, sans-serif;
            color: #fff;
        }
        .header {
            margin-bottom: 20px;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 8px;
        }
        h1 {
            margin: 0 0 10px 0;
            font-size: 24px;
        }
        .status {
            color: #888;
            font-size: 14px;
        }
        .status.connected {
            color: #4ade80;
        }
        #screen {
            border: 2px solid #333;
            border-radius: 8px;
            background: #000;
            max-width: 100%;
        }
        .controls {
            margin-top: 15px;
            display: flex;
            gap: 10px;
        }
        button {
            padding: 10px 20px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }
        button:hover {
            background: #2563eb;
        }
        button:disabled {
            background: #555;
            cursor: not-allowed;
        }
        .error {
            color: #ef4444;
            margin-top: 10px;
            padding: 10px;
            background: #2a1a1a;
            border-radius: 6px;
            border-left: 3px solid #ef4444;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Leadfeeder Scraper - Live View</h1>
        <div class="status" id="status">Connecting to VNC server...</div>
    </div>

    <canvas id="screen" width="1920" height="1080"></canvas>

    <div class="controls">
        <button id="connectBtn" onclick="connect()">Connect</button>
        <button id="disconnectBtn" onclick="disconnect()" disabled>Disconnect</button>
    </div>

    <div id="error" class="error" style="display:none;"></div>

    <script type="module">
        import RFB from 'https://cdn.jsdelivr.net/npm/@novnc/novnc@1.4.0/core/rfb.js';

        // Make RFB available globally
        window.RFB = RFB;

        // Wait for DOM to be ready
        document.addEventListener('DOMContentLoaded', initVNC);

        function initVNC() {
        let rfb = null;
        const canvas = document.getElementById('screen');
        const status = document.getElementById('status');
        const error = document.getElementById('error');
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');

        function showError(msg) {
            error.textContent = msg;
            error.style.display = 'block';
        }

        function hideError() {
            error.style.display = 'none';
        }

        function updateStatus(msg, connected = false) {
            status.textContent = msg;
            status.className = connected ? 'status connected' : 'status';
        }

        function connect() {
            hideError();
            updateStatus('Connecting...');
            connectBtn.disabled = true;

            try {
                // Use same protocol as page (ws:// for http://, wss:// for https://)
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const host = window.location.host; // includes port if present

                // Connect through Flask proxy endpoint
                const wsUrl = `${protocol}//${host}/vnc-websocket`;

                rfb = new RFB(canvas, wsUrl, {
                    credentials: { password: '' }
                });

                rfb.addEventListener('connect', () => {
                    updateStatus('✓ Connected - Watching browser live', true);
                    connectBtn.disabled = true;
                    disconnectBtn.disabled = false;
                });

                rfb.addEventListener('disconnect', () => {
                    updateStatus('Disconnected');
                    connectBtn.disabled = false;
                    disconnectBtn.disabled = true;
                    rfb = null;
                });

                rfb.addEventListener('credentialsrequired', () => {
                    showError('Password required (not configured)');
                });

                rfb.addEventListener('securityfailure', (e) => {
                    showError('Security failure: ' + e.detail.reason);
                    connectBtn.disabled = false;
                });

                rfb.scaleViewport = true;
                rfb.resizeSession = false;

            } catch (err) {
                showError('Connection failed: ' + err.message);
                connectBtn.disabled = false;
            }
        }

        function disconnect() {
            if (rfb) {
                rfb.disconnect();
                rfb = null;
            }
            updateStatus('Disconnected');
            connectBtn.disabled = false;
            disconnectBtn.disabled = true;
        }

        // Auto-connect after init
        setTimeout(connect, 1000);

        // Make functions globally available
        window.connect = connect;
        window.disconnect = disconnect;
        }
    </script>
</body>
</html>
    """


@app.route("/api/scheduler/status", methods=["GET"])
def scheduler_status():
    """Get background job scheduler status."""
    from scheduler import get_scheduler_status

    status = get_scheduler_status()
    return jsonify(status)


@app.route("/api/scheduler/jobs", methods=["GET"])
def list_scheduled_jobs():
    """List all scheduled jobs and their status."""
    from scheduler import get_scheduler_status, get_job_history

    status = get_scheduler_status()
    history = get_job_history(limit=20)

    return jsonify({
        "scheduler": status,
        "history": history
    })


@app.route("/api/scheduler/jobs/<job_id>/run", methods=["POST"])
def run_job_manually(job_id):
    """Manually trigger a scheduled job."""
    from scheduler import run_job_now

    result = run_job_now(job_id)
    return jsonify(result)


@app.route("/api/apollo/account", methods=["GET"])
def apollo_account_info():
    """Get Apollo API account information and credits."""
    try:
        from apollo_enrichment import ApolloEnricher
        enricher = ApolloEnricher()

        if not enricher.api_key:
            return jsonify({
                "configured": False,
                "error": "Apollo API key not configured"
            }), 200

        account_info = enricher.get_account_info()

        if account_info:
            return jsonify({
                "configured": True,
                **account_info
            })
        else:
            return jsonify({
                "configured": True,
                "error": "Failed to fetch account info"
            }), 500

    except Exception as e:
        logger.error(f"Error fetching Apollo account info: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/webhooks/apollo/phone-reveal", methods=["POST"])
def apollo_phone_reveal_webhook():
    """
    Receive phone number reveals from Apollo waterfall enrichment.

    Apollo sends POST requests to this endpoint when phone numbers are revealed
    via waterfall enrichment. The payload contains the person data with phone numbers.
    """
    payload = get_request_json()

    try:
        # Log the webhook receipt
        logger.info(f"Received Apollo phone reveal webhook for person_id: {payload.get('person', {}).get('id')}")

        person = payload.get("person", {})
        person_id = person.get("id")

        if not person_id:
            return jsonify({"error": "Missing person_id in webhook payload"}), 400

        # Extract phone numbers
        phone_numbers = person.get("phone_numbers", [])

        if not phone_numbers:
            logger.warning(f"No phone numbers in webhook for person_id: {person_id}")
            return jsonify({"status": "no_phones"}), 200

        # Update the person record in the database
        with get_connection() as conn:
            # Check if person exists
            existing = conn.execute(
                "SELECT * FROM leads_people WHERE apollo_id = ?",
                (person_id,)
            ).fetchone()

            if existing:
                # Update phone number
                primary_phone = phone_numbers[0].get("raw_number", "")
                conn.execute("""
                    UPDATE leads_people
                    SET phone = ?,
                        phone_numbers = ?,
                        updated_at = ?
                    WHERE apollo_id = ?
                """, (
                    primary_phone,
                    json.dumps(phone_numbers),
                    utc_now(),
                    person_id
                ))

                logger.info(f"Updated phone number for person_id: {person_id}")
                return jsonify({"status": "updated", "person_id": person_id}), 200
            else:
                logger.warning(f"Person not found in database: {person_id}")
                # Store the webhook data for later processing
                conn.execute("""
                    INSERT INTO apollo_webhook_queue (
                        webhook_type, person_id, payload, received_at, processed
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    "phone_reveal",
                    person_id,
                    json.dumps(payload),
                    utc_now(),
                    0
                ))
                return jsonify({"status": "queued", "person_id": person_id}), 200

    except Exception as e:
        logger.error(f"Error processing Apollo phone webhook: {e}")
        return jsonify({"error": str(e)}), 500


# Serve React frontend (catch-all route - must be last)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """Serve React frontend for all non-API routes."""
    from flask import send_from_directory

    # If path is a file in static folder, serve it
    if path and (DASHBOARD_DIST / path).exists():
        return send_from_directory(str(DASHBOARD_DIST), path)
    # Otherwise serve index.html (for React Router)
    return send_from_directory(str(DASHBOARD_DIST), 'index.html')


# Initialize scheduler on app start
def init_visitor_scheduler():
    """Initialize the background scheduler for visitor tracking jobs."""
    from scheduler import start_scheduler
    try:
        start_scheduler()
        logger.info("Visitor tracking scheduler started")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


if __name__ == "__main__":
    ensure_seed_data()
    init_visitor_scheduler()
    host = "127.0.0.1"
    port = choose_port()
    try:
        app.run(host=host, port=port)
    except OSError as exc:
        if port != 0:
            app.run(host=host, port=0)
        else:
            raise exc
