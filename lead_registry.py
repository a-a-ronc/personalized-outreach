import hashlib
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import Config

logger = logging.getLogger(__name__)
from lead_scoring import stable_hash, title_bucket, normalize_text

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "leads.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(timestamp: str):
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads_company (
                company_key TEXT PRIMARY KEY,
                apollo_org_id TEXT UNIQUE,
                domain_norm TEXT UNIQUE,
                name TEXT,
                industry TEXT,
                employee_count INTEGER,
                estimated_revenue TEXT,
                technologies TEXT,
                tech_stack_hash TEXT,
                wms_system TEXT,
                equipment_signals TEXT,
                job_postings_count INTEGER,
                job_postings_relevant INTEGER,
                locations TEXT,
                enriched_at TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads_people (
                person_key TEXT PRIMARY KEY,
                apollo_person_id TEXT UNIQUE,
                linkedin_url_norm TEXT UNIQUE,
                email_norm TEXT UNIQUE,
                company_key TEXT,
                first_name TEXT,
                last_name TEXT,
                title TEXT,
                seniority TEXT,
                department TEXT,
                email TEXT,
                email_status TEXT,
                phone TEXT,
                job_start_date TEXT,
                icp_match TEXT,
                icp_score INTEGER,
                strategy_assignment TEXT,
                readiness_score INTEGER,
                source TEXT,
                enriched_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                enrichment_request_hash TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_people_company_key ON leads_people(company_key)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outreach_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_key TEXT,
                campaign_id TEXT,
                sequence_step INTEGER,
                sent_at TEXT,
                status TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outreach_person ON outreach_log(person_key)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apollo_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_key TEXT,
                campaign_id TEXT,
                status TEXT,
                request_hash TEXT,
                reveal_personal_emails INTEGER,
                reveal_phone_number INTEGER,
                note TEXT,
                created_at TEXT,
                updated_at TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_apollo_queue_status ON apollo_queue(status)"
        )


def upgrade_schema_v2():
    """Upgrade database schema to v2 with multi-channel sequence support."""
    with get_connection() as conn:
        # Add LinkedIn and call tracking to leads_people
        try:
            conn.execute("ALTER TABLE leads_people ADD COLUMN linkedin_connection_status TEXT")
        except:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE leads_people ADD COLUMN linkedin_connected_at TEXT")
        except:
            pass

        try:
            conn.execute("ALTER TABLE leads_people ADD COLUMN last_call_attempt_at TEXT")
        except:
            pass

        try:
            conn.execute("ALTER TABLE leads_people ADD COLUMN last_call_status TEXT")
        except:
            pass

        # Add channel tracking to outreach_log
        try:
            conn.execute("ALTER TABLE outreach_log ADD COLUMN channel TEXT DEFAULT 'email'")
        except:
            pass

        try:
            conn.execute("ALTER TABLE outreach_log ADD COLUMN next_action_at TEXT")
        except:
            pass

        try:
            conn.execute("ALTER TABLE outreach_log ADD COLUMN action_metadata TEXT")
        except:
            pass

        # Create sequences table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sequences (
                id TEXT PRIMARY KEY,
                campaign_id TEXT,
                name TEXT,
                steps TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Create sequence_steps table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sequence_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id TEXT,
                step_order INTEGER,
                step_type TEXT,
                delay_days INTEGER,
                channel TEXT,
                template_data TEXT,
                conditions TEXT,
                created_at TEXT
            )
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sequence_steps_sequence_id ON sequence_steps(sequence_id)"
        )

        # Create signatures table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signatures (
                id TEXT PRIMARY KEY,
                user_email TEXT,
                name TEXT,
                html_content TEXT,
                plain_text_content TEXT,
                is_default INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
        """)


def upgrade_schema_v3():
    """Upgrade database schema to v3 with sequence templates support."""
    with get_connection() as conn:
        # Add sender_email column to sequences table
        try:
            conn.execute("ALTER TABLE sequences ADD COLUMN sender_email TEXT")
        except:
            pass  # Column already exists

        # Create sequence_templates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sequence_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                steps TEXT,
                is_system_template INTEGER DEFAULT 0,
                created_by TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Insert default system templates
        import json
        from datetime import datetime

        now = datetime.utcnow().isoformat()

        default_templates = [
            {
                "id": "3pl-cold-outreach",
                "name": "3PL Cold Outreach",
                "description": "5-step sequence targeting 3PL decision makers with email and phone follow-up",
                "category": "3pl",
                "steps": json.dumps([
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_1",
                        "subject": "Warehouse automation for {{company_name}}",
                        "body": "Hi {{first_name}},\n\n{{personalization_sentence}}\n\nWe help 3PLs like {{company_name}} automate warehouse operations to cut labor costs by 40% and boost throughput 3x.\n\nWorth a 15-minute call?\n\nBest,\n{{sender_name}}"
                    },
                    {
                        "type": "wait",
                        "delay_days": 3
                    },
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_2",
                        "subject": "Re: {{company_name}} automation",
                        "body": "Hi {{first_name}},\n\nFollowing up on my email about warehouse automation for {{company_name}}.\n\nWe recently helped a 200k sq ft 3PL reduce pick times by 60%. Happy to share the case study.\n\nOpen to a quick call this week?\n\n{{sender_name}}"
                    },
                    {
                        "type": "wait",
                        "delay_days": 4
                    },
                    {
                        "type": "call",
                        "delay_days": 0,
                        "script": "Hi {{first_name}}, this is {{sender_name}} from Intralog. I sent you a couple emails about warehouse automation for {{company_name}}. I wanted to reach out personally because we're seeing great results with 3PLs - our clients are cutting labor costs by 40% on average. Do you have 2 minutes to discuss how this could work for {{company_name}}?"
                    }
                ]),
                "is_system_template": 1,
                "created_at": now,
                "updated_at": now
            },
            {
                "id": "warehouse-automation-full",
                "name": "Warehouse Automation - Full Sequence",
                "description": "7-step omnichannel sequence with email, call, and LinkedIn outreach",
                "category": "warehouse_automation",
                "steps": json.dumps([
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_1",
                        "subject": "Warehouse automation opportunity at {{company_name}}",
                        "body": "{{personalization_sentence}}\n\nWe specialize in warehouse automation for companies like {{company_name}}. Our clients typically see 3x throughput gains and 40% labor cost reduction.\n\nOpen to exploring this?\n\n{{sender_name}}"
                    },
                    {
                        "type": "wait",
                        "delay_days": 3
                    },
                    {
                        "type": "linkedin_connect",
                        "delay_days": 0,
                        "message": "Hi {{first_name}}, I saw your role at {{company_name}} and thought I'd connect. We work with warehouse operations teams on automation projects."
                    },
                    {
                        "type": "wait",
                        "delay_days": 2
                    },
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_2",
                        "subject": "Re: Warehouse automation at {{company_name}}",
                        "body": "Hi {{first_name}},\n\nWanted to follow up - are you currently exploring warehouse automation solutions?\n\nWe recently completed a project for a company with similar {{pain_theme}} challenges. Happy to share details.\n\n{{sender_name}}"
                    },
                    {
                        "type": "wait",
                        "delay_days": 4
                    },
                    {
                        "type": "call",
                        "delay_days": 0,
                        "script": "Hi {{first_name}}, {{sender_name}} from Intralog. Quick call about warehouse automation at {{company_name}}. I know {{pain_theme}} is a common challenge in your industry. We've helped similar companies achieve 3x throughput gains. Do you have 5 minutes to discuss?"
                    },
                    {
                        "type": "wait",
                        "delay_days": 3
                    },
                    {
                        "type": "linkedin_message",
                        "delay_days": 0,
                        "message": "Hi {{first_name}}, tried to reach you by email and phone about warehouse automation for {{company_name}}. Worth a quick call? Let me know if you're open to discussing."
                    }
                ]),
                "is_system_template": 1,
                "created_at": now,
                "updated_at": now
            },
            {
                "id": "quick-email-followup",
                "name": "Quick Email Follow-up",
                "description": "Simple 2-email sequence for warm leads or quick outreach",
                "category": "logistics",
                "steps": json.dumps([
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_1",
                        "subject": "Quick question about {{company_name}}",
                        "body": "Hi {{first_name}},\n\n{{personalization_sentence}}\n\nWe help logistics companies like {{company_name}} streamline operations and cut costs through automation.\n\nWorth a brief conversation?\n\n{{sender_name}}"
                    },
                    {
                        "type": "wait",
                        "delay_days": 4
                    },
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_2",
                        "subject": "Re: {{company_name}}",
                        "body": "Hi {{first_name}},\n\nCircling back on my previous email. We've been helping companies in your space achieve significant operational improvements.\n\nOpen to a 10-minute intro call?\n\n{{sender_name}}"
                    }
                ]),
                "is_system_template": 1,
                "created_at": now,
                "updated_at": now
            },
            {
                "id": "enterprise-multi-touch",
                "name": "Enterprise Multi-Touch",
                "description": "9-step enterprise sequence with all channels for high-value accounts",
                "category": "warehouse_automation",
                "steps": json.dumps([
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_1"
                    },
                    {
                        "type": "wait",
                        "delay_days": 2
                    },
                    {
                        "type": "linkedin_connect",
                        "delay_days": 0,
                        "message": "Hi {{first_name}}, reaching out regarding warehouse automation opportunities at {{company_name}}."
                    },
                    {
                        "type": "wait",
                        "delay_days": 3
                    },
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_2"
                    },
                    {
                        "type": "wait",
                        "delay_days": 3
                    },
                    {
                        "type": "call",
                        "delay_days": 0,
                        "script": "Enterprise-focused call script for {{first_name}} at {{company_name}} regarding {{pain_theme}}."
                    },
                    {
                        "type": "wait",
                        "delay_days": 2
                    },
                    {
                        "type": "linkedin_message",
                        "delay_days": 0,
                        "message": "Following up on my outreach - would love to connect about automation at {{company_name}}."
                    },
                    {
                        "type": "wait",
                        "delay_days": 5
                    },
                    {
                        "type": "email",
                        "delay_days": 0,
                        "template": "email_1",
                        "subject": "Final follow-up: {{company_name}} automation",
                        "body": "Hi {{first_name}},\n\nLast follow-up from me. If warehouse automation isn't a priority right now, totally understand.\n\nIf it becomes relevant in the future, feel free to reach out.\n\n{{sender_name}}"
                    }
                ]),
                "is_system_template": 1,
                "created_at": now,
                "updated_at": now
            }
        ]

        # Insert templates only if they don't exist
        for template in default_templates:
            existing = conn.execute(
                "SELECT id FROM sequence_templates WHERE id = ?",
                (template["id"],)
            ).fetchone()

            if not existing:
                conn.execute("""
                    INSERT INTO sequence_templates
                    (id, name, description, category, steps, is_system_template, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    template["id"],
                    template["name"],
                    template["description"],
                    template["category"],
                    template["steps"],
                    template["is_system_template"],
                    template["created_at"],
                    template["updated_at"]
                ))


def normalize_email(email: str) -> str:
    return normalize_text(email)


def normalize_domain(domain: str) -> str:
    if not domain:
        return ""
    domain = normalize_text(domain)
    for prefix in ["http://", "https://"]:
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_linkedin(url: str) -> str:
    if not url:
        return ""
    normalized = normalize_text(url)
    if "?" in normalized:
        normalized = normalized.split("?")[0]
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def compute_company_key(apollo_org_id: str, domain_norm: str, name: str = "", hq_city: str = "", hq_state: str = "") -> str:
    if apollo_org_id:
        return f"apollo_org:{apollo_org_id}"
    if domain_norm:
        return f"domain:{domain_norm}"
    fallback = f"{normalize_text(name)}|{normalize_text(hq_city)}|{normalize_text(hq_state)}"
    return f"hash:{stable_hash(fallback)}"


def compute_person_key(
    apollo_person_id: str,
    linkedin_url_norm: str,
    email_norm: str,
    first_name: str,
    last_name: str,
    company_domain: str,
    title: str
) -> str:
    if apollo_person_id:
        return f"apollo_person:{apollo_person_id}"
    if linkedin_url_norm:
        return f"linkedin:{linkedin_url_norm}"
    if email_norm:
        return f"email:{email_norm}"
    fallback = "|".join(
        [
            normalize_text(first_name),
            normalize_text(last_name),
            normalize_domain(company_domain),
            title_bucket(title)
        ]
    )
    return f"hash:{stable_hash(fallback)}"


def upsert_company(company: dict) -> str:
    apollo_org_id = company.get("apollo_org_id") or company.get("company_id") or ""
    domain_norm = normalize_domain(company.get("domain", ""))
    company_key = compute_company_key(apollo_org_id, domain_norm, company.get("name", ""))
    now = utc_now()

    values = {
        "company_key": company_key,
        "apollo_org_id": apollo_org_id or None,
        "domain_norm": domain_norm or None,
        "name": company.get("name", ""),
        "industry": company.get("industry", ""),
        "employee_count": int(company.get("employee_count", 0) or 0),
        "estimated_revenue": company.get("estimated_revenue", ""),
        "technologies": ", ".join(company.get("technologies", [])),
        "tech_stack_hash": stable_hash(" ".join(company.get("technologies", []))) if company.get("technologies") else "",
        "wms_system": company.get("wms_system", ""),
        "equipment_signals": ", ".join(company.get("equipment_signals", [])),
        "job_postings_count": int(company.get("job_postings_count", 0) or 0),
        "job_postings_relevant": int(company.get("job_postings_relevant", 0) or 0),
        "locations": ", ".join(company.get("locations", [])),
        "enriched_at": company.get("enriched_at") or None,
        "created_at": now,
        "updated_at": now
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO leads_company (
                company_key, apollo_org_id, domain_norm, name, industry, employee_count,
                estimated_revenue, technologies, tech_stack_hash, wms_system, equipment_signals,
                job_postings_count, job_postings_relevant, locations, enriched_at, created_at, updated_at
            ) VALUES (
                :company_key, :apollo_org_id, :domain_norm, :name, :industry, :employee_count,
                :estimated_revenue, :technologies, :tech_stack_hash, :wms_system, :equipment_signals,
                :job_postings_count, :job_postings_relevant, :locations, :enriched_at, :created_at, :updated_at
            )
            ON CONFLICT(company_key) DO UPDATE SET
                apollo_org_id=excluded.apollo_org_id,
                domain_norm=excluded.domain_norm,
                name=excluded.name,
                industry=excluded.industry,
                employee_count=excluded.employee_count,
                estimated_revenue=excluded.estimated_revenue,
                technologies=excluded.technologies,
                tech_stack_hash=excluded.tech_stack_hash,
                wms_system=excluded.wms_system,
                equipment_signals=excluded.equipment_signals,
                job_postings_count=excluded.job_postings_count,
                job_postings_relevant=excluded.job_postings_relevant,
                locations=excluded.locations,
                enriched_at=COALESCE(excluded.enriched_at, leads_company.enriched_at),
                updated_at=excluded.updated_at
            """,
            values
        )
    return company_key


def upsert_person(person: dict) -> str:
    email_norm = normalize_email(person.get("email", ""))
    linkedin_norm = normalize_linkedin(person.get("linkedin_url", ""))
    company_domain = person.get("company_domain", "")
    person_key = compute_person_key(
        person.get("apollo_person_id", ""),
        linkedin_norm,
        email_norm,
        person.get("first_name", ""),
        person.get("last_name", ""),
        company_domain,
        person.get("title", "")
    )
    now = utc_now()

    values = {
        "person_key": person_key,
        "apollo_person_id": person.get("apollo_person_id") or None,
        "linkedin_url_norm": linkedin_norm or None,
        "email_norm": email_norm or None,
        "company_key": person.get("company_key"),
        "first_name": person.get("first_name", ""),
        "last_name": person.get("last_name", ""),
        "title": person.get("title", ""),
        "seniority": person.get("seniority", ""),
        "department": person.get("department", ""),
        "email": person.get("email", ""),
        "email_status": person.get("email_status", ""),
        "phone": person.get("phone", ""),
        "job_start_date": person.get("job_start_date", ""),
        "icp_match": person.get("icp_match", ""),
        "icp_score": int(person.get("icp_score", 0) or 0),
        "strategy_assignment": person.get("strategy_assignment", ""),
        "readiness_score": int(person.get("readiness_score", 0) or 0),
        "source": person.get("source", ""),
        "enriched_at": person.get("enriched_at") or None,
        "created_at": now,
        "updated_at": now,
        "enrichment_request_hash": person.get("enrichment_request_hash", "")
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO leads_people (
                person_key, apollo_person_id, linkedin_url_norm, email_norm, company_key,
                first_name, last_name, title, seniority, department, email, email_status,
                phone, job_start_date, icp_match, icp_score, strategy_assignment, readiness_score,
                source, enriched_at, created_at, updated_at, enrichment_request_hash
            ) VALUES (
                :person_key, :apollo_person_id, :linkedin_url_norm, :email_norm, :company_key,
                :first_name, :last_name, :title, :seniority, :department, :email, :email_status,
                :phone, :job_start_date, :icp_match, :icp_score, :strategy_assignment, :readiness_score,
                :source, :enriched_at, :created_at, :updated_at, :enrichment_request_hash
            )
            ON CONFLICT(person_key) DO UPDATE SET
                apollo_person_id=COALESCE(excluded.apollo_person_id, leads_people.apollo_person_id),
                linkedin_url_norm=COALESCE(excluded.linkedin_url_norm, leads_people.linkedin_url_norm),
                email_norm=COALESCE(excluded.email_norm, leads_people.email_norm),
                company_key=COALESCE(excluded.company_key, leads_people.company_key),
                first_name=COALESCE(excluded.first_name, leads_people.first_name),
                last_name=COALESCE(excluded.last_name, leads_people.last_name),
                title=COALESCE(excluded.title, leads_people.title),
                seniority=COALESCE(excluded.seniority, leads_people.seniority),
                department=COALESCE(excluded.department, leads_people.department),
                email=COALESCE(excluded.email, leads_people.email),
                email_status=COALESCE(excluded.email_status, leads_people.email_status),
                phone=COALESCE(excluded.phone, leads_people.phone),
                job_start_date=COALESCE(excluded.job_start_date, leads_people.job_start_date),
                icp_match=COALESCE(excluded.icp_match, leads_people.icp_match),
                icp_score=MAX(leads_people.icp_score, excluded.icp_score),
                strategy_assignment=COALESCE(excluded.strategy_assignment, leads_people.strategy_assignment),
                readiness_score=MAX(leads_people.readiness_score, excluded.readiness_score),
                source=COALESCE(excluded.source, leads_people.source),
                enriched_at=COALESCE(excluded.enriched_at, leads_people.enriched_at),
                updated_at=excluded.updated_at,
                enrichment_request_hash=COALESCE(excluded.enrichment_request_hash, leads_people.enrichment_request_hash)
            """,
            values
        )
    return person_key


def get_person_by_key(person_key: str):
    if not person_key:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM leads_people WHERE person_key = ?", (person_key,)
        ).fetchone()
    return dict(row) if row else None


def get_person_by_email(email: str):
    email_norm = normalize_email(email)
    if not email_norm:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM leads_people WHERE email_norm = ?", (email_norm,)
        ).fetchone()
    return dict(row) if row else None


def get_company_by_key(company_key: str):
    if not company_key:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM leads_company WHERE company_key = ?", (company_key,)
        ).fetchone()
    return dict(row) if row else None


def is_suppressed(person_key: str) -> bool:
    if not person_key:
        return False
    suppression_window = datetime.now(timezone.utc) - timedelta(days=Config.APOLLO_SUPPRESSION_DAYS)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT sent_at FROM outreach_log WHERE person_key = ? ORDER BY sent_at DESC LIMIT 1",
            (person_key,)
        ).fetchone()
    if not row:
        return False
    last_sent = parse_timestamp(row["sent_at"])
    if not last_sent:
        return False
    return last_sent >= suppression_window


def log_outreach(person_key: str, campaign_id: str, sequence_step: int, status: str):
    if not person_key:
        return
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO outreach_log (person_key, campaign_id, sequence_step, sent_at, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (person_key, campaign_id, sequence_step, utc_now(), status)
        )


def insert_queue_record(person_key: str, campaign_id: str, status: str, request_hash: str,
                        reveal_personal_emails: bool, reveal_phone_number: bool, note: str = "") -> int:
    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO apollo_queue (
                person_key, campaign_id, status, request_hash,
                reveal_personal_emails, reveal_phone_number, note, created_at, updated_at, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_key,
                campaign_id,
                status,
                request_hash,
                1 if reveal_personal_emails else 0,
                1 if reveal_phone_number else 0,
                note,
                now,
                now,
                ""
            )
        )
        row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
    return int(row["id"]) if row else 0


def enqueue_enrichment(person_key: str, campaign_id: str, request_hash: str,
                       reveal_personal_emails: bool, reveal_phone_number: bool, note: str = "") -> int:
    return insert_queue_record(
        person_key,
        campaign_id,
        "queued",
        request_hash,
        reveal_personal_emails,
        reveal_phone_number,
        note
    )


def update_queue_status(queue_id: int, status: str, error: str = ""):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE apollo_queue
            SET status = ?, updated_at = ?, error = ?
            WHERE id = ?
            """,
            (status, utc_now(), error, queue_id)
        )


def get_queue_items(status: str = "queued", limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM apollo_queue WHERE status = ? ORDER BY created_at ASC LIMIT ?",
            (status, limit)
        ).fetchall()
    return [dict(row) for row in rows]


def recent_request_hash(person_key: str, request_hash: str, ttl_days: int) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT updated_at FROM apollo_queue
            WHERE person_key = ? AND request_hash = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (person_key, request_hash)
        ).fetchone()
    if not row:
        return False
    updated_at = parse_timestamp(row["updated_at"])
    if not updated_at:
        return False
    return updated_at >= cutoff


def get_queue_summary(campaign_id: str = "") -> dict:
    with get_connection() as conn:
        params = ()
        where = ""
        if campaign_id:
            where = "WHERE campaign_id = ?"
            params = (campaign_id,)
        rows = conn.execute(
            f"SELECT status, COUNT(*) as count FROM apollo_queue {where} GROUP BY status",
            params
        ).fetchall()
    summary = {row["status"]: row["count"] for row in rows}
    return summary


def get_people_for_campaign(campaign_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, c.name as company_name, c.industry as company_industry,
                   c.employee_count as employee_count, c.technologies as technologies,
                   c.wms_system as wms_system, c.equipment_signals as equipment_signals,
                   c.job_postings_relevant as job_postings_relevant
            FROM apollo_queue q
            JOIN leads_people p ON q.person_key = p.person_key
            LEFT JOIN leads_company c ON p.company_key = c.company_key
            WHERE q.campaign_id = ? AND q.status IN ('enriched', 'skipped')
            ORDER BY q.updated_at ASC
            """,
            (campaign_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def calculate_enrichment_hash(person_key: str, reveal_personal_emails: bool, reveal_phone_number: bool) -> str:
    payload = f"{person_key}|{int(reveal_personal_emails)}|{int(reveal_phone_number)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade_schema_v4():
    """Upgrade database schema to v4 with editable sender signatures and sequence settings."""
    with get_connection() as conn:
        # Create sender_signatures table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sender_signatures (
                email TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT,
                phone TEXT,
                signature_html TEXT,
                persona_context TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Create sequence_settings table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sequence_settings (
                sequence_id TEXT PRIMARY KEY,
                personalization_mode TEXT DEFAULT 'signal_based',
                include_signature INTEGER DEFAULT 1,
                FOREIGN KEY (sequence_id) REFERENCES sequences(id)
            )
        """)

        # Initialize sender signatures from config if not exists
        from config import Config
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"

        for profile in Config.SENDER_PROFILES:
            conn.execute("""
                INSERT OR IGNORE INTO sender_signatures
                (email, full_name, title, company, phone, signature_html, persona_context, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile["email"],
                profile["full_name"],
                profile["title"],
                profile.get("company", "Intralog"),
                profile.get("phone", ""),
                profile.get("signature", ""),
                "",  # persona_context will be added later
                now,
                now
            ))

        logger.info("✓ Schema upgraded to v4: sender_signatures and sequence_settings tables created")


def upgrade_schema_v5():
    """Upgrade database schema to v5 with sender warmup settings and email tracking."""
    with get_connection() as conn:
        # Add warmup columns to sender_signatures if they don't exist
        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN warmup_enabled INTEGER DEFAULT 0")
            logger.info("Added warmup_enabled column to sender_signatures")
        except Exception:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN daily_limit INTEGER DEFAULT 50")
            logger.info("Added daily_limit column to sender_signatures")
        except Exception:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN ramp_schedule TEXT DEFAULT 'conservative'")
            logger.info("Added ramp_schedule column to sender_signatures")
        except Exception:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN signature_text TEXT")
            logger.info("Added signature_text column to sender_signatures")
        except Exception:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN warmup_started_at TEXT")
            logger.info("Added warmup_started_at column to sender_signatures")
        except Exception:
            pass  # Column already exists

        # Create emails table if not exists for tracking sent emails
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                campaign_id TEXT,
                sequence_id TEXT,
                lead_id TEXT,
                sender_email TEXT,
                recipient_email TEXT,
                subject TEXT,
                body_html TEXT,
                body_plain TEXT,
                status TEXT DEFAULT 'pending',
                sent_at TEXT,
                opened_at TEXT,
                clicked_at TEXT,
                replied_at TEXT,
                bounced_at TEXT,
                created_at TEXT,
                FOREIGN KEY (lead_id) REFERENCES leads(id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        """)

        # Create indexes for faster queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender_email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_status ON emails(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_lead ON emails(lead_id)")

        logger.info("✓ Schema upgraded to v5: sender warmup settings and emails tracking table")


def upgrade_schema_v6():
    """Upgrade database schema to v6 with website visitor identification tables."""
    with get_connection() as conn:
        # Raw visitor tracking data - stores all visits permanently
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitor_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_id TEXT UNIQUE,
                ip_address TEXT,
                user_agent TEXT,
                page_url TEXT,
                referrer TEXT,
                session_id TEXT,
                timestamp TEXT,
                created_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_raw_ip ON visitor_raw(ip_address)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_raw_timestamp ON visitor_raw(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_raw_session ON visitor_raw(session_id)")

        # MaxMind/DIY IP resolution results
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitor_ip_resolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT,
                source TEXT,
                company_name TEXT,
                domain TEXT,
                industry TEXT,
                employee_count INTEGER,
                city TEXT,
                region TEXT,
                country TEXT,
                isp TEXT,
                organization TEXT,
                is_datacenter INTEGER DEFAULT 0,
                is_vpn INTEGER DEFAULT 0,
                confidence_score REAL,
                resolved_at TEXT,
                raw_response TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_ip_resolution_ip ON visitor_ip_resolution(ip_address)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_ip_resolution_domain ON visitor_ip_resolution(domain)")

        # Leadfeeder scraped data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leadfeeder_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                leadfeeder_id TEXT UNIQUE,
                company_name TEXT,
                domain TEXT,
                industry TEXT,
                employee_count INTEGER,
                country TEXT,
                page_views INTEGER,
                visit_duration INTEGER,
                first_visit_at TEXT,
                last_visit_at TEXT,
                pages_visited TEXT,
                referrer TEXT,
                scraped_at TEXT,
                expires_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leadfeeder_visits_domain ON leadfeeder_visits(domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leadfeeder_visits_expires ON leadfeeder_visits(expires_at)")

        # Reconciled visitor companies (final identified companies)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitor_companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT UNIQUE,
                company_name TEXT,
                domain TEXT,
                industry TEXT,
                employee_count INTEGER,
                country TEXT,
                source TEXT,
                confidence_score REAL,
                total_visits INTEGER DEFAULT 0,
                total_page_views INTEGER DEFAULT 0,
                first_visit_at TEXT,
                last_visit_at TEXT,
                apollo_enriched INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_companies_domain ON visitor_companies(domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_companies_last_visit ON visitor_companies(last_visit_at)")

        # Visit sessions (aggregated visits per company)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitor_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_company_id INTEGER,
                session_id TEXT,
                ip_address TEXT,
                pages TEXT,
                page_count INTEGER,
                duration_seconds INTEGER,
                referrer TEXT,
                user_agent TEXT,
                started_at TEXT,
                ended_at TEXT,
                FOREIGN KEY (visitor_company_id) REFERENCES visitor_companies(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_sessions_company ON visitor_sessions(visitor_company_id)")

        # Scheduled jobs tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT UNIQUE,
                last_run_at TEXT,
                next_run_at TEXT,
                status TEXT,
                error TEXT,
                run_count INTEGER DEFAULT 0
            )
        """)

        # Integration status tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS integration_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_name TEXT UNIQUE,
                status TEXT,
                last_sync_at TEXT,
                error_message TEXT,
                config_valid INTEGER DEFAULT 0
            )
        """)

        logger.info("✓ Schema upgraded to v6: website visitor identification tables")


def upgrade_schema_v7():
    """Upgrade database schema to v7 with email warmup tracking tables."""
    with get_connection() as conn:
        # Warmup sends tracking - records every email sent (warmup + campaign)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warmup_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_email TEXT NOT NULL,
                recipient_email TEXT,
                send_type TEXT DEFAULT 'campaign',
                warmup_day INTEGER,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'sent',
                FOREIGN KEY (sender_email) REFERENCES sender_signatures(email)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warmup_sends_sender ON warmup_sends(sender_email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warmup_sends_date ON warmup_sends(sent_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warmup_sends_type ON warmup_sends(send_type)")

        # Add warmup_day column to sender_signatures if it doesn't exist
        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN warmup_day INTEGER DEFAULT 1")
            logger.info("Added warmup_day column to sender_signatures")
        except Exception:
            pass  # Column already exists

        # Add current_daily_limit column (calculated from schedule)
        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN current_daily_limit INTEGER DEFAULT 50")
            logger.info("Added current_daily_limit column to sender_signatures")
        except Exception:
            pass  # Column already exists

        # Add warmup_service column (for future Mailwarm integration)
        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN warmup_service TEXT")
            logger.info("Added warmup_service column to sender_signatures")
        except Exception:
            pass  # Column already exists

        # Add warmup_service_id column
        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN warmup_service_id TEXT")
            logger.info("Added warmup_service_id column to sender_signatures")
        except Exception:
            pass  # Column already exists

        # Add last_warmup_check column (for daily advancement)
        try:
            conn.execute("ALTER TABLE sender_signatures ADD COLUMN last_warmup_check TEXT")
            logger.info("Added last_warmup_check column to sender_signatures")
        except Exception:
            pass  # Column already exists

        logger.info("✓ Schema upgraded to v7: email warmup tracking tables")
