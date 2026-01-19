import hashlib
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import Config
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
