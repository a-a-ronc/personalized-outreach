"""
Visitor Reconciliation Module

Merges data from DIY IP tracking and Leadfeeder scraping using the priority logic:
1. If DIY matches Leadfeeder -> Save DIY (they match)
2. If DIY differs from Leadfeeder -> Trust Leadfeeder (better data)
3. If only DIY has data -> Use DIY
4. If only Leadfeeder has data -> Use Leadfeeder
5. If neither identified -> Keep raw visit data for future analysis
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

from lead_registry import get_connection, utc_now, normalize_domain

logger = logging.getLogger(__name__)


def compute_visitor_company_key(domain: str, company_name: str = "") -> str:
    """Generate a unique key for a visitor company."""
    if domain:
        return f"visitor:{normalize_domain(domain)}"
    if company_name:
        # Fallback to company name hash
        import hashlib
        name_hash = hashlib.sha256(company_name.lower().encode()).hexdigest()[:12]
        return f"visitor:name:{name_hash}"
    return None


def string_similarity(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings (0.0 to 1.0)."""
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def domains_match(domain1: str, domain2: str) -> bool:
    """Check if two domains are effectively the same."""
    if not domain1 or not domain2:
        return False

    d1 = normalize_domain(domain1)
    d2 = normalize_domain(domain2)

    # Exact match
    if d1 == d2:
        return True

    # One is subdomain of another
    if d1.endswith(f".{d2}") or d2.endswith(f".{d1}"):
        return True

    return False


def companies_match(diy_data: dict, lf_data: dict) -> bool:
    """
    Determine if DIY and Leadfeeder data refer to the same company.

    Uses domain matching primarily, falls back to company name similarity.
    """
    # Domain match is strongest signal
    if domains_match(diy_data.get("domain"), lf_data.get("domain")):
        return True

    # Company name similarity as fallback
    diy_name = diy_data.get("company_name") or diy_data.get("organization")
    lf_name = lf_data.get("company_name")

    if diy_name and lf_name:
        similarity = string_similarity(diy_name, lf_name)
        if similarity >= 0.8:  # 80% similarity threshold
            return True

    return False


def choose_best_source(diy_data: dict, lf_data: dict) -> dict:
    """
    Choose the best data source based on priority logic.

    Priority:
    1. If both match -> use DIY (same result)
    2. If both different -> trust Leadfeeder (better data)
    3. If only DIY -> use DIY
    4. If only Leadfeeder -> use Leadfeeder
    """
    has_diy = bool(diy_data and (diy_data.get("company_name") or diy_data.get("domain")))
    has_lf = bool(lf_data and (lf_data.get("company_name") or lf_data.get("domain")))

    if has_diy and has_lf:
        if companies_match(diy_data, lf_data):
            # They match - use DIY but merge any extra fields from Leadfeeder
            result = {**diy_data}
            result["source"] = "diy"
            result["match_type"] = "matched"

            # Merge missing fields from Leadfeeder
            for key in ["industry", "employee_count", "country"]:
                if not result.get(key) and lf_data.get(key):
                    result[key] = lf_data[key]

            return result
        else:
            # They differ - trust Leadfeeder
            result = {**lf_data}
            result["source"] = "leadfeeder"
            result["match_type"] = "leadfeeder_preferred"
            return result

    elif has_diy:
        result = {**diy_data}
        result["source"] = "diy"
        result["match_type"] = "diy_only"
        return result

    elif has_lf:
        result = {**lf_data}
        result["source"] = "leadfeeder"
        result["match_type"] = "leadfeeder_only"
        return result

    return None


def get_diy_identifications(days: int = 7) -> list:
    """Get DIY IP resolution data from the last N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                vir.*,
                COUNT(DISTINCT vr.visit_id) as visit_count,
                MAX(vr.timestamp) as last_visit,
                MIN(vr.timestamp) as first_visit
            FROM visitor_ip_resolution vir
            JOIN visitor_raw vr ON vir.ip_address = vr.ip_address
            WHERE vir.resolved_at >= ?
            AND vir.confidence_score > 0.2
            AND vir.is_datacenter = 0
            GROUP BY vir.ip_address
            ORDER BY visit_count DESC
        """, (cutoff,)).fetchall()

    return [dict(row) for row in rows]


def get_leadfeeder_data() -> list:
    """Get active Leadfeeder data (not expired)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM leadfeeder_visits
            WHERE expires_at > datetime('now')
            OR scraped_at > datetime('now', '-7 days')
            ORDER BY page_views DESC
        """).fetchall()

    return [dict(row) for row in rows]


def reconcile_visitor_data():
    """
    Main reconciliation function.

    Matches DIY and Leadfeeder data and creates/updates visitor_companies records.
    """
    logger.info("Starting visitor data reconciliation...")

    diy_data = get_diy_identifications()
    lf_data = get_leadfeeder_data()

    logger.info(f"Found {len(diy_data)} DIY identifications and {len(lf_data)} Leadfeeder companies")

    # Track which Leadfeeder entries have been matched
    matched_lf_ids = set()
    reconciled_count = 0
    now = utc_now()

    # First pass: Match DIY data with Leadfeeder
    for diy in diy_data:
        # Find matching Leadfeeder entry
        matching_lf = None
        for lf in lf_data:
            if lf["id"] not in matched_lf_ids and companies_match(diy, lf):
                matching_lf = lf
                matched_lf_ids.add(lf["id"])
                break

        # Choose best source
        best_data = choose_best_source(diy, matching_lf)

        if best_data:
            upsert_visitor_company(best_data, diy.get("visit_count", 1), now)
            reconciled_count += 1

    # Second pass: Add unmatched Leadfeeder entries
    for lf in lf_data:
        if lf["id"] not in matched_lf_ids:
            best_data = choose_best_source(None, lf)
            if best_data:
                upsert_visitor_company(best_data, lf.get("page_views", 1), now)
                reconciled_count += 1

    logger.info(f"Reconciliation complete. Processed {reconciled_count} companies.")
    return reconciled_count


def upsert_visitor_company(data: dict, visit_count: int, timestamp: str):
    """Create or update a visitor company record."""
    company_key = compute_visitor_company_key(
        data.get("domain"),
        data.get("company_name")
    )

    if not company_key:
        return None

    # Calculate confidence based on data quality
    confidence = calculate_reconciled_confidence(data)

    with get_connection() as conn:
        # Check if exists
        existing = conn.execute(
            "SELECT * FROM visitor_companies WHERE company_key = ?",
            (company_key,)
        ).fetchone()

        if existing:
            # Update existing
            conn.execute("""
                UPDATE visitor_companies SET
                    company_name = COALESCE(?, company_name),
                    domain = COALESCE(?, domain),
                    industry = COALESCE(?, industry),
                    employee_count = COALESCE(?, employee_count),
                    country = COALESCE(?, country),
                    source = ?,
                    confidence_score = ?,
                    total_visits = total_visits + ?,
                    last_visit_at = ?,
                    updated_at = ?
                WHERE company_key = ?
            """, (
                data.get("company_name"),
                data.get("domain"),
                data.get("industry"),
                data.get("employee_count"),
                data.get("country"),
                data.get("source", "reconciled"),
                confidence,
                visit_count,
                data.get("last_visit") or timestamp,
                timestamp,
                company_key
            ))
        else:
            # Insert new
            conn.execute("""
                INSERT INTO visitor_companies (
                    company_key, company_name, domain, industry,
                    employee_count, country, source, confidence_score,
                    total_visits, total_page_views, first_visit_at,
                    last_visit_at, apollo_enriched, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company_key,
                data.get("company_name"),
                data.get("domain"),
                data.get("industry"),
                data.get("employee_count"),
                data.get("country"),
                data.get("source", "reconciled"),
                confidence,
                visit_count,
                data.get("page_views", visit_count),
                data.get("first_visit") or timestamp,
                data.get("last_visit") or timestamp,
                0,
                timestamp,
                timestamp
            ))

    return company_key


def calculate_reconciled_confidence(data: dict) -> float:
    """Calculate confidence score for reconciled data."""
    score = 0.0

    # Source bonus
    if data.get("source") == "leadfeeder":
        score += 0.3  # Leadfeeder data is generally more reliable
    elif data.get("source") == "diy":
        score += 0.2

    # Matched data bonus
    if data.get("match_type") == "matched":
        score += 0.3  # Both sources agree

    # Data completeness
    if data.get("company_name"):
        score += 0.15
    if data.get("domain"):
        score += 0.15
    if data.get("industry"):
        score += 0.05
    if data.get("employee_count"):
        score += 0.05

    return min(score, 1.0)


def get_visitor_companies(
    limit: int = 50,
    offset: int = 0,
    source: str = None,
    min_visits: int = None,
    days: int = None,
    enriched_only: bool = False
) -> list:
    """
    Get visitor companies with filtering options.

    Args:
        limit: Maximum number of results
        offset: Offset for pagination
        source: Filter by source ('diy', 'leadfeeder', 'reconciled')
        min_visits: Minimum visit count filter
        days: Only include companies visited in last N days
        enriched_only: Only return Apollo-enriched companies
    """
    conditions = []
    params = []

    if source:
        conditions.append("source = ?")
        params.append(source)

    if min_visits:
        conditions.append("total_visits >= ?")
        params.append(min_visits)

    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conditions.append("last_visit_at >= ?")
        params.append(cutoff)

    if enriched_only:
        conditions.append("apollo_enriched = 1")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT * FROM visitor_companies
            {where_clause}
            ORDER BY last_visit_at DESC
            LIMIT ? OFFSET ?
        """, params).fetchall()

        total = conn.execute(f"""
            SELECT COUNT(*) as count FROM visitor_companies
            {where_clause.replace('LIMIT ? OFFSET ?', '')}
        """, params[:-2] if conditions else []).fetchone()["count"]

    return {
        "companies": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_visitor_company_detail(company_key: str) -> dict:
    """Get detailed information about a visitor company including sessions."""
    with get_connection() as conn:
        # Get company
        company = conn.execute(
            "SELECT * FROM visitor_companies WHERE company_key = ?",
            (company_key,)
        ).fetchone()

        if not company:
            return None

        company = dict(company)

        # Get sessions
        sessions = conn.execute("""
            SELECT * FROM visitor_sessions
            WHERE visitor_company_id = ?
            ORDER BY started_at DESC
            LIMIT 50
        """, (company["id"],)).fetchall()

        company["sessions"] = [dict(s) for s in sessions]

        # Get associated people (if Apollo enriched)
        if company.get("apollo_enriched"):
            # Find people by domain
            domain = company.get("domain")
            if domain:
                people = conn.execute("""
                    SELECT p.*, c.name as company_name
                    FROM leads_people p
                    LEFT JOIN leads_company c ON p.company_key = c.company_key
                    WHERE c.domain_norm = ?
                    LIMIT 20
                """, (normalize_domain(domain),)).fetchall()
                company["contacts"] = [dict(p) for p in people]

    return company


def get_reconciliation_stats() -> dict:
    """Get statistics about visitor data reconciliation."""
    with get_connection() as conn:
        # By source
        by_source = conn.execute("""
            SELECT source, COUNT(*) as count
            FROM visitor_companies
            GROUP BY source
        """).fetchall()

        # Total companies
        total = conn.execute(
            "SELECT COUNT(*) as count FROM visitor_companies"
        ).fetchone()["count"]

        # Enriched count
        enriched = conn.execute(
            "SELECT COUNT(*) as count FROM visitor_companies WHERE apollo_enriched = 1"
        ).fetchone()["count"]

        # Average confidence
        avg_confidence = conn.execute(
            "SELECT AVG(confidence_score) as avg FROM visitor_companies"
        ).fetchone()["avg"] or 0

        # Top industries
        industries = conn.execute("""
            SELECT industry, COUNT(*) as count
            FROM visitor_companies
            WHERE industry IS NOT NULL
            GROUP BY industry
            ORDER BY count DESC
            LIMIT 10
        """).fetchall()

    return {
        "total_companies": total,
        "by_source": {row["source"]: row["count"] for row in by_source},
        "enriched_count": enriched,
        "average_confidence": round(avg_confidence, 2),
        "top_industries": [{"industry": row["industry"], "count": row["count"]} for row in industries]
    }
