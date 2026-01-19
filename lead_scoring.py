import hashlib
from datetime import datetime, timezone


LOGISTICS_KEYWORDS = [
    "3pl",
    "logistics",
    "distribution",
    "warehousing",
    "supply chain",
    "third party",
    "fulfillment"
]

COLD_STORAGE_KEYWORDS = [
    "cold",
    "frozen",
    "food",
    "protein",
    "dairy",
    "meat",
    "produce"
]

MANUFACTURING_KEYWORDS = [
    "manufactur",
    "industrial",
    "plant"
]

ECOMMERCE_KEYWORDS = [
    "e-commerce",
    "ecommerce",
    "retail",
    "online"
]

OPS_TITLE_KEYWORDS = [
    "operations",
    "warehouse",
    "logistics",
    "supply chain",
    "distribution"
]

QA_TITLE_KEYWORDS = [
    "quality",
    "qa",
    "food safety",
    "compliance"
]

CONTROLS_KEYWORDS = [
    "controls",
    "automation",
    "systems",
    "robotics"
]

ERP_KEYWORDS = [
    "sap",
    "oracle",
    "netsuite",
    "infor",
    "epicor"
]

WMS_KEYWORDS = [
    "manhattan",
    "blue yonder",
    "jda",
    "sap",
    "oracle",
    "infor",
    "highjump",
    "wms"
]


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def parse_employee_count(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).split(",") if item.strip()]


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def title_bucket(title: str) -> str:
    text = normalize_text(title)
    if any(keyword in text for keyword in ["chief", "ceo", "coo", "cfo", "president"]):
        return "c_suite"
    if any(keyword in text for keyword in ["vp", "vice president", "director", "head"]):
        return "vp_director"
    if any(keyword in text for keyword in ["manager", "supervisor", "lead"]):
        return "manager"
    if any(keyword in text for keyword in ["engineer", "engineering", "systems", "automation", "controls"]):
        return "engineer"
    return "unknown"


def compute_job_tenure_years(job_start_date: str) -> float | None:
    if not job_start_date:
        return None
    try:
        start = datetime.fromisoformat(job_start_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    delta = now - start
    return delta.days / 365.25


def compute_automation_readiness(features: dict) -> int:
    score = 0
    if features.get("wms_present"):
        score += 20
    if features.get("enterprise_wms"):
        score += 10
    if features.get("controls_roles_hiring"):
        score += 20
    if features.get("employee_count", 0) >= 400:
        score += 15
    tenure = features.get("job_tenure_years")
    if tenure is not None and tenure < 3:
        score += 10
    if features.get("job_postings_relevant", 0) >= 3:
        score += 10
    if features.get("tech_stack_depth", 0) >= 8:
        score += 5
    if features.get("automation_signals"):
        score += 10
    return min(score, 100)


def extract_features(person_record: dict, company_record: dict) -> dict:
    industry = normalize_text(company_record.get("industry", ""))
    employee_count = parse_employee_count(company_record.get("employee_count", 0))
    technologies = ensure_list(company_record.get("technologies"))
    tech_stack_depth = len(technologies)
    tech_lower = normalize_text(" ".join(technologies))
    wms_present = contains_any(tech_lower, WMS_KEYWORDS)
    enterprise_wms = any(keyword in tech_lower for keyword in ["manhattan", "blue yonder", "jda", "sap", "oracle"])
    automation_signals = ensure_list(company_record.get("equipment_signals"))
    automation_present = any(signal in ["automation", "asrs", "agv_amr", "sortation", "shuttle"] for signal in automation_signals)
    controls_roles_hiring = bool(company_record.get("controls_roles_hiring"))
    job_postings_relevant = int(company_record.get("job_postings_relevant", 0) or 0)
    job_postings_count = int(company_record.get("job_postings_count", 0) or 0)
    locations = ensure_list(company_record.get("locations"))

    title = person_record.get("title", "")
    title_lower = normalize_text(title)
    seniority = normalize_text(person_record.get("seniority", ""))
    department = normalize_text(person_record.get("department", ""))
    job_tenure_years = compute_job_tenure_years(person_record.get("job_start_date"))

    return {
        "industry": industry,
        "employee_count": employee_count,
        "technologies": technologies,
        "tech_stack_depth": tech_stack_depth,
        "wms_present": wms_present,
        "enterprise_wms": enterprise_wms,
        "controls_roles_hiring": controls_roles_hiring,
        "automation_signals": automation_present,
        "job_postings_relevant": job_postings_relevant,
        "job_postings_count": job_postings_count,
        "locations": locations,
        "title": title,
        "title_lower": title_lower,
        "seniority": seniority,
        "department": department,
        "job_tenure_years": job_tenure_years
    }


def score_icp(features: dict) -> tuple[str, int, dict]:
    scores = {"ICP 1": 0, "ICP 2": 0, "ICP 3": 0, "ICP 4": 0, "ICP 5": 0}
    reasons = {key: [] for key in scores}

    industry = features.get("industry", "")
    employee_count = features.get("employee_count", 0)
    title_lower = features.get("title_lower", "")
    job_postings_relevant = features.get("job_postings_relevant", 0)
    tech_stack_depth = features.get("tech_stack_depth", 0)

    if contains_any(industry, LOGISTICS_KEYWORDS):
        scores["ICP 1"] += 2
        reasons["ICP 1"].append("logistics_industry")
    if 200 <= employee_count <= 800:
        scores["ICP 1"] += 1
        reasons["ICP 1"].append("mid_headcount")
    if features.get("wms_present"):
        scores["ICP 1"] += 1
        reasons["ICP 1"].append("wms_present")
    if contains_any(title_lower, OPS_TITLE_KEYWORDS):
        scores["ICP 1"] += 1
        reasons["ICP 1"].append("ops_title")

    if contains_any(industry, COLD_STORAGE_KEYWORDS):
        scores["ICP 2"] += 2
        reasons["ICP 2"].append("cold_storage_industry")
    if 150 <= employee_count <= 600:
        scores["ICP 2"] += 1
        reasons["ICP 2"].append("mid_headcount")
    if contains_any(title_lower, OPS_TITLE_KEYWORDS) or contains_any(title_lower, QA_TITLE_KEYWORDS):
        scores["ICP 2"] += 1
        reasons["ICP 2"].append("ops_or_qa_title")
    if tech_stack_depth <= 5:
        scores["ICP 2"] += 1
        reasons["ICP 2"].append("lighter_tech_stack")

    if contains_any(industry, MANUFACTURING_KEYWORDS):
        scores["ICP 3"] += 2
        reasons["ICP 3"].append("manufacturing_industry")
    if contains_any(normalize_text(" ".join(features.get("technologies", []))), ERP_KEYWORDS):
        scores["ICP 3"] += 1
        reasons["ICP 3"].append("erp_present")
    if not features.get("wms_present"):
        scores["ICP 3"] += 1
        reasons["ICP 3"].append("limited_wms")

    if contains_any(industry, ECOMMERCE_KEYWORDS):
        scores["ICP 4"] += 2
        reasons["ICP 4"].append("ecommerce_industry")
    if employee_count >= 500:
        scores["ICP 4"] += 1
        reasons["ICP 4"].append("large_headcount")
    if features.get("wms_present"):
        scores["ICP 4"] += 1
        reasons["ICP 4"].append("wms_present")
    if job_postings_relevant >= 5:
        scores["ICP 4"] += 1
        reasons["ICP 4"].append("growth_hiring")
    if len(features.get("locations", [])) >= 2:
        scores["ICP 4"] += 1
        reasons["ICP 4"].append("multi_site")

    if features.get("wms_present"):
        scores["ICP 5"] += 1
        reasons["ICP 5"].append("wms_present")
    if features.get("controls_roles_hiring"):
        scores["ICP 5"] += 1
        reasons["ICP 5"].append("controls_hiring")
    if employee_count >= 400:
        scores["ICP 5"] += 1
        reasons["ICP 5"].append("large_headcount")
    tenure = features.get("job_tenure_years")
    if tenure is not None and tenure < 3:
        scores["ICP 5"] += 1
        reasons["ICP 5"].append("recent_hire")
    if features.get("automation_signals"):
        scores["ICP 5"] += 1
        reasons["ICP 5"].append("automation_signals")

    best_icp = max(scores, key=scores.get)
    if scores[best_icp] == 0:
        if contains_any(industry, MANUFACTURING_KEYWORDS):
            best_icp = "ICP 3"
        elif contains_any(industry, COLD_STORAGE_KEYWORDS):
            best_icp = "ICP 2"
        elif contains_any(industry, ECOMMERCE_KEYWORDS):
            best_icp = "ICP 4"
        elif contains_any(industry, LOGISTICS_KEYWORDS):
            best_icp = "ICP 1"
        else:
            best_icp = "ICP 1"

    return best_icp, scores.get(best_icp, 0), reasons.get(best_icp, [])


def assign_strategy(icp_match: str, readiness_score: int, threshold: int = 65, hybrid_band: int = 7) -> str:
    icp_match = icp_match.strip()
    if icp_match in ["ICP 1", "ICP 3"]:
        return "conventional"
    if icp_match == "ICP 2":
        return "semi_auto"
    if icp_match == "ICP 4":
        return "full_auto"
    if icp_match == "ICP 5":
        if readiness_score >= threshold + hybrid_band:
            return "full_auto"
        if readiness_score <= threshold - hybrid_band:
            return "semi_auto"
        return "hybrid"
    return "conventional"


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
