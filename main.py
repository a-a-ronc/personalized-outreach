import argparse
import json
import sys
from pathlib import Path
import pandas as pd
import logging
from config import Config
from personalization_engine import batch_generate

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ROLE_LEVEL_KEYWORDS = {
    "c_suite": ["ceo", "coo", "cfo", "president", "chief"],
    "vp_director": ["vp", "vice president", "director", "head"],
    "manager": ["manager", "supervisor", "lead"],
    "engineer": ["engineer", "engineering", "systems", "industrial", "automation", "controls"]
}

PAIN_LIBRARY = {
    "ICP 1": {
        "c_suite": [
            {"theme": "reconfiguration", "statement": "Racking layouts tend to fall behind client mix shifts long before warehouse growth plans do."},
            {"theme": "labor", "statement": "Labor balance usually tightens when new accounts and seasonal volume hit at the same time."}
        ],
        "vp_director": [
            {"theme": "reconfiguration", "statement": "Pick paths and racking layouts often need re-slotting as SKU velocity changes."},
            {"theme": "throughput", "statement": "Throughput ceilings usually show up at the handoff between storage and picking."}
        ],
        "manager": [
            {"theme": "labor", "statement": "Labor coverage can get uneven when replenishment and picking compete for the same crews."},
            {"theme": "reconfiguration", "statement": "Layout changes tend to lag client onboarding and create short-term congestion."}
        ],
        "engineer": [
            {"theme": "reconfiguration", "statement": "Slotting and layout adjustments usually take more time than the client mix allows."},
            {"theme": "integration", "statement": "Controls and WMS handoffs can become brittle once new storage zones are added."}
        ]
    },
    "ICP 2": {
        "c_suite": [
            {"theme": "space", "statement": "Cold storage operations often hit density limits before automation plans are ready."},
            {"theme": "throughput", "statement": "Throughput targets tend to collide with pallet access constraints in cold environments."}
        ],
        "vp_director": [
            {"theme": "space", "statement": "Pallet density and access usually start competing as cold volumes expand."},
            {"theme": "integration", "statement": "Automation readiness can be delayed by integration risk in temperature-controlled zones."}
        ],
        "manager": [
            {"theme": "space", "statement": "Space utilization can tighten quickly when inbound and staging overlap in cold areas."},
            {"theme": "labor", "statement": "Labor planning gets tough when travel time and staging keep shifting in cold storage."}
        ],
        "engineer": [
            {"theme": "space", "statement": "High-density storage choices usually force tradeoffs between access time and pallet density."},
            {"theme": "integration", "statement": "Controls integration tends to slow once cold zones add automation in phases."}
        ]
    },
    "ICP 3": {
        "c_suite": [
            {"theme": "integration", "statement": "Material flow integration often becomes the pacing item as manufacturing expands."},
            {"theme": "throughput", "statement": "Throughput bottlenecks usually shift from production to internal flow over time."}
        ],
        "vp_director": [
            {"theme": "integration", "statement": "Material flow handoffs often create the longest tail as lines and storage expand."},
            {"theme": "reconfiguration", "statement": "Mezzanine and flow changes usually lag expansion and create interim inefficiency."}
        ],
        "manager": [
            {"theme": "throughput", "statement": "Internal flow tends to slow where storage and production exchange materials."},
            {"theme": "reconfiguration", "statement": "Layout tweaks can become frequent once expansion adds parallel staging areas."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Equipment integration points often become the limiting factor as lines scale."},
            {"theme": "throughput", "statement": "Conveyance and staging handoffs usually set the practical throughput ceiling."}
        ]
    },
    "ICP 4": {
        "c_suite": [
            {"theme": "throughput", "statement": "Throughput targets usually hit a ceiling before the network design does."},
            {"theme": "integration", "statement": "Controls coordination often becomes the pacing item as sortation expands."}
        ],
        "vp_director": [
            {"theme": "throughput", "statement": "Conveyor and sortation handoffs often cap throughput as volume peaks."},
            {"theme": "integration", "statement": "Controls and WMS coordination tends to lag once sortation grows."}
        ],
        "manager": [
            {"theme": "throughput", "statement": "Peak throughput often gets constrained by merge points and induction flow."},
            {"theme": "labor", "statement": "Labor allocation can get tight when induction and outbound staffing swing daily."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Controls timing between conveyor zones tends to be the first bottleneck."},
            {"theme": "throughput", "statement": "Sortation merges usually set the upper bound on throughput."}
        ]
    },
    "ICP 5": {
        "c_suite": [
            {"theme": "space", "statement": "High-density storage targets usually come before automation programs are stable."},
            {"theme": "integration", "statement": "Automation integration risk often sets the pace for phased upgrades."}
        ],
        "vp_director": [
            {"theme": "space", "statement": "Density and access tradeoffs tend to sharpen as volumes scale."},
            {"theme": "integration", "statement": "Integration planning can slow down phased automation rollouts."}
        ],
        "manager": [
            {"theme": "space", "statement": "Storage density can tighten quickly when inbound staging expands."},
            {"theme": "labor", "statement": "Labor coverage tends to get uneven around automated and manual zones."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Integration between automation and controls tends to surface first in phased rollouts."},
            {"theme": "space", "statement": "Dense storage layouts usually trade off access time and retrieval sequence."}
        ]
    },
    "DEFAULT": {
        "unknown": [
            {"theme": "throughput", "statement": "Throughput often tightens where storage and picking exchange materials."},
            {"theme": "integration", "statement": "System handoffs can become the longest tail as operations scale."}
        ]
    }
}

PAIN_THEME_KEYWORDS = {
    "throughput": ["throughput", "sortation", "merge", "induction", "shipping", "shipping dock", "case handling"],
    "space": ["cold storage", "density", "deep-lane", "pallet shuttle", "asrs", "vlm", "space", "high-density"],
    "labor": ["labor", "staffing", "shift", "training", "manual", "ergonomic"],
    "reconfiguration": ["re-slot", "slotting", "layout", "mezzanine", "pick module", "racking"],
    "integration": ["integration", "controls", "wms", "automation", "handoff", "interface"]
}

EQUIPMENT_ANCHOR_KEYWORDS = {
    "conveyor": ["conveyor"],
    "sortation": ["sortation", "sorter"],
    "pallet_shuttle": ["pallet shuttle", "pallet shuttles"],
    "racking": ["racking", "rack", "shelving"],
    "mezzanine": ["mezzanine"],
    "amr_agv": ["amr", "agv", "autonomous", "mobile robot"],
    "asrs": ["asrs", "shuttle", "miniload"],
    "vlm": ["vlm", "vertical lift"],
    "wms": ["wms", "warehouse management"]
}

CTA_ACTIONS = {
    "throughput": "sanity-check the flow",
    "space": "compare layout options",
    "labor": "pressure-test labor assumptions",
    "reconfiguration": "map re-slotting options",
    "integration": "walk through handoffs"
}


def extract_first_name(full_name: str) -> str:
    """
    Extract first name from full name field

    Args:
        full_name: Full name string (e.g., "John Smith")

    Returns:
        First name or "there" as fallback
    """
    if not full_name or pd.isna(full_name):
        return "there"

    # Take first word before space
    first_name = str(full_name).strip().split()[0]
    return first_name if first_name else "there"


def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def classify_role_level(job_title: str) -> str:
    title = normalize_text(job_title).lower()
    if not title:
        return "unknown"

    for level, keywords in ROLE_LEVEL_KEYWORDS.items():
        if any(keyword in title for keyword in keywords):
            return level
    return "unknown"


def extract_equipment_anchors(equipment: str, notes: str) -> list[str]:
    combined = f"{normalize_text(equipment)} {normalize_text(notes)}".lower()
    anchors = []
    for anchor, keywords in EQUIPMENT_ANCHOR_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            anchors.append(anchor)
    return anchors


def infer_pain_theme(icp_match: str, role_level: str, equipment: str, notes: str) -> str:
    combined = f"{normalize_text(equipment)} {normalize_text(notes)}".lower()
    for theme, keywords in PAIN_THEME_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            return theme

    icp_entry = PAIN_LIBRARY.get(icp_match, {})
    role_entry = icp_entry.get(role_level) or PAIN_LIBRARY.get("DEFAULT", {}).get("unknown", [])
    if role_entry:
        return role_entry[0]["theme"]
    return "throughput"


def select_pain_statement(icp_match: str, role_level: str, pain_theme: str) -> str:
    role_entry = PAIN_LIBRARY.get(icp_match, {}).get(role_level, [])
    if not role_entry:
        role_entry = PAIN_LIBRARY.get("DEFAULT", {}).get("unknown", [])

    for entry in role_entry:
        if entry["theme"] == pain_theme:
            return entry["statement"]

    return role_entry[0]["statement"] if role_entry else "Throughput often tightens where storage and picking exchange materials."


def compute_icp_confidence(icp_match: str, industry: str, role_level: str, equipment_anchors: list[str]) -> str:
    score = 0
    if icp_match in PAIN_LIBRARY:
        score += 2
    industry_clean = normalize_text(industry).lower()
    if industry_clean and industry_clean not in ["other", "misc", "general"]:
        score += 1
    if role_level != "unknown":
        score += 1
    if equipment_anchors:
        score += 1

    if score >= 4:
        return "high"
    if score == 3:
        return "medium"
    return "low"


def confidence_to_certainty(icp_confidence: str) -> str:
    if icp_confidence == "high":
        return "strong"
    if icp_confidence == "medium":
        return "moderate"
    return "light"


def build_credibility_anchor(equipment_category: str) -> str:
    return f"We work on {equipment_category}."


def build_cta_line(pain_theme: str, icp_confidence: str, followup: bool = False) -> tuple[str, str]:
    action = CTA_ACTIONS.get(pain_theme, "sanity-check the flow")
    label = action.replace("the ", "")

    if icp_confidence == "high":
        line = f"Can we {action} this week?" if followup else f"Can we {action} next week?"
    elif icp_confidence == "medium":
        line = f"I can {action} if that helps." if followup else f"If useful, I can {action}."
    else:
        line = f"If helpful, I can {action}."

    return label, line


def build_reinforcement_line(pain_theme: str, industry: str, icp_confidence: str) -> str:
    industry_text = normalize_text(industry) or "operations"
    if icp_confidence == "high":
        adverb = "almost always"
    elif icp_confidence == "medium":
        adverb = "usually"
    else:
        adverb = "can"

    lines = {
        "throughput": f"In {industry_text} flow, the tight spot {adverb} sits between storage and picking.",
        "space": f"In {industry_text} facilities, density and access {adverb} pull against each other.",
        "labor": f"In {industry_text} ops, labor balance {adverb} tightens around picking and replenishment.",
        "reconfiguration": f"In {industry_text} ops, layout changes {adverb} lag shifts in SKU mix.",
        "integration": f"In {industry_text} ops, system handoffs {adverb} become the longest tail."
    }

    return lines.get(pain_theme, lines["throughput"])


def get_equipment_offer(icp_match: str, equipment: str, notes: str) -> tuple[str, str]:
    """
    Dynamically select equipment offer based on lead context

    Args:
        icp_match: ICP segment (e.g., "ICP 1", "ICP 2", etc.)
        equipment: Equipment description from dataset
        notes: ICP notes with additional context

    Returns:
        (equipment_category, software_mention)
    """
    # Normalize inputs for matching
    equipment_lower = str(equipment).lower()
    notes_lower = str(notes).lower()
    combined_context = f"{equipment_lower} {notes_lower}"

    # Priority 1: High-Density Storage Systems
    if any(keyword in equipment_lower for keyword in ["pallet shuttle", "push-back", "pallet flow", "deep-lane", "pushback"]):
        equipment_category = "high-density storage systems - pallet shuttles, push-back rack, and deep-lane flow"
        if icp_match in ["ICP 2", "ICP 5"]:
            software_mention = " - and we built DensityPro to orchestrate the staging logic that most WMS systems miss"
        else:
            software_mention = ""
        return (equipment_category, software_mention)

    # Priority 2: Conveyor & Sortation
    if any(keyword in equipment_lower for keyword in ["conveyor", "sortation", "case handling"]):
        equipment_category = "case and pallet conveyor systems with integrated sortation"
        if icp_match == "ICP 4" and "national" in combined_context:
            software_mention = " - and partner with Lully to handle the WMS orchestration that makes throughput targets actually achievable"
        else:
            software_mention = ""
        return (equipment_category, software_mention)

    # Priority 3: Pick Module & Racking Systems
    if any(keyword in equipment_lower for keyword in ["pick module", "pick", "racking", "shelving", "mezzanine"]):
        equipment_category = "racking systems and pick modules"
        if icp_match in ["ICP 1", "ICP 3"]:
            software_mention = " - and we've built slotting software (Warehousr) to help you reconfigure layouts as demand changes"
        else:
            software_mention = ""
        return (equipment_category, software_mention)

    # Priority 4: AMR/AGV Automation
    if any(keyword in equipment_lower for keyword in ["amr", "agv", "autonomous", "mobile robot"]):
        equipment_category = "AMR and AGV systems for material flow automation"
        software_mention = ""
        return (equipment_category, software_mention)

    # Fallback: General Material Handling
    equipment_category = "material handling systems - from racking and conveyors to automation integration"
    software_mention = ""
    return (equipment_category, software_mention)


def get_subject_line_by_icp(icp_match: str, industry: str) -> str:
    """
    Get ICP-specific subject line variant

    Args:
        icp_match: ICP segment (e.g., "ICP 1", "ICP 2", etc.)
        industry: Industry classification

    Returns:
        Customized subject line
    """
    # Map ICP segments to specific subject lines
    icp_subjects = {
        "ICP 1": "Quick thought on pick module efficiency",
        "ICP 2": "Quick thought on cold storage density",
        "ICP 3": "Quick thought on material flow layout",
        "ICP 4": "Quick thought on throughput scaling",
        "ICP 5": "Quick thought on high-density automation"
    }

    # Return ICP-specific subject or default
    if icp_match in icp_subjects:
        return icp_subjects[icp_match]
    else:
        # Default fallback using industry
        return f"Quick thought on {industry} operations"


def load_email_template(template_name: str) -> tuple[str, str]:
    """
    Load email template and extract subject and body

    Returns:
        (subject, body_template)
    """
    template_path = Path(__file__).parent / "templates" / template_name
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split on first newline after "Subject:"
    lines = content.split("\n")
    subject = ""
    body_lines = []

    for i, line in enumerate(lines):
        if line.startswith("Subject:"):
            subject = line.replace("Subject:", "").strip()
            # Body starts after the subject line and a blank line
            body_lines = lines[i + 2:]  # Skip subject and blank line
            break

    body = "\n".join(body_lines)
    return subject, body


def fill_template(template: str, data: dict) -> str:
    """Fill template placeholders with data"""
    result = template
    for key, value in data.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def prepare_personalization_controls(df: pd.DataFrame) -> pd.DataFrame:
    role_levels = []
    icp_confidences = []
    certainty_levels = []
    pain_themes = []
    pain_statements = []
    equipment_anchors = []

    for _, row in df.iterrows():
        job_title = normalize_text(row.get("Job title", ""))
        industry = normalize_text(row.get("Industry", ""))
        icp_match = normalize_text(row.get("ICP Match", ""))
        notes = normalize_text(row.get("Notes", ""))
        equipment = normalize_text(row.get("Equipment", ""))

        role_level = classify_role_level(job_title)
        anchors = extract_equipment_anchors(equipment, notes)
        pain_theme = infer_pain_theme(icp_match, role_level, equipment, notes)
        pain_statement = select_pain_statement(icp_match, role_level, pain_theme)
        icp_confidence = compute_icp_confidence(icp_match, industry, role_level, anchors)
        certainty_level = confidence_to_certainty(icp_confidence)

        role_levels.append(role_level)
        icp_confidences.append(icp_confidence)
        certainty_levels.append(certainty_level)
        pain_themes.append(pain_theme)
        pain_statements.append(pain_statement)
        equipment_anchors.append(", ".join(anchors))

    df["role_level"] = role_levels
    df["icp_confidence"] = icp_confidences
    df["certainty_level"] = certainty_levels
    df["pain_theme"] = pain_themes
    df["pain_statement"] = pain_statements
    df["equipment_anchor"] = equipment_anchors

    return df


def generate_campaigns(input_path: str, output_path: str, limit: int = None, raise_on_error: bool = False):
    """
    Main function to generate personalized email campaigns

    Args:
        input_path: Path to input CSV with leads
        output_path: Path to output CSV with campaigns
        limit: Optional limit on number of leads to process
        raise_on_error: Raise exceptions instead of exiting (useful for web apps)
    """
    logger.info("=" * 60)
    logger.info("Personalized Outreach Campaign Generator")
    logger.info("=" * 60)

    # Validate configuration
    try:
        Config.validate()
        logger.info("✓ Configuration validated")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("\nPlease create a .env file based on .env.example")
        if raise_on_error:
            raise ValueError(str(e))
        sys.exit(1)

    # Load input CSV
    logger.info(f"\nLoading leads from: {input_path}")
    try:
        df = pd.read_csv(input_path)
        logger.info(f"✓ Loaded {len(df)} leads")
    except Exception as e:
        logger.error(f"Failed to load CSV: {e}")
        if raise_on_error:
            raise RuntimeError(f"Failed to load CSV: {e}")
        sys.exit(1)

    # Apply limit if specified
    if limit:
        df = df.head(limit)
        logger.info(f"✓ Limited to {limit} leads for testing")

    # Validate required columns (new dataset format)
    required_columns = ["Company", "Industry", "Email address", "Full name"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        logger.error(f"Missing required columns: {', '.join(missing)}")
        logger.error(f"Available columns: {', '.join(df.columns)}")
        if raise_on_error:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        sys.exit(1)

    # Ensure optional columns exist
    if "Notes" not in df.columns:
        df["Notes"] = ""
        logger.info("⚠ No 'Notes' column found - using empty strings")

    if "ICP Match" not in df.columns:
        df["ICP Match"] = ""
        logger.info("⚠ No 'ICP Match' column found - using empty strings")

    if "Equipment" not in df.columns:
        df["Equipment"] = ""
        logger.info("⚠ No 'Equipment' column found - using empty strings")

    logger.info("✓ Required columns present")

    # Prepare deterministic personalization controls
    df = prepare_personalization_controls(df)

    # Generate personalization sentences
    logger.info("\n" + "=" * 60)
    logger.info("Generating personalization sentences...")
    logger.info("=" * 60)

    df = batch_generate(df)

    # Load email templates
    logger.info("\nLoading email templates...")
    email_1_subject, email_1_body = load_email_template("email_1.txt")
    email_2_subject, email_2_body = load_email_template("email_2.txt")
    logger.info("✓ Templates loaded")

    # Generate campaign rows
    logger.info("\nGenerating campaign output...")
    logger.info(f"Rotating between {len(Config.SENDER_PROFILES)} senders:")
    for profile in Config.SENDER_PROFILES:
        logger.info(f"  - {profile['full_name']} ({profile['title']})")

    campaign_rows = []

    for idx, row in df.iterrows():
        company_name = row["Company"]
        email_address = row["Email address"]
        full_name = row["Full name"]
        job_title = normalize_text(row.get("Job title", ""))
        job_title_display = job_title if job_title else "operations leader"
        industry = normalize_text(row.get("Industry", ""))
        icp_match = normalize_text(row.get("ICP Match", ""))
        icp_notes = normalize_text(row.get("Notes", ""))
        equipment = normalize_text(row.get("Equipment", ""))
        personalization = row["personalization_sentence"]
        pain_theme = row.get("pain_theme", "throughput")
        icp_confidence = row.get("icp_confidence", "low")
        certainty_level = row.get("certainty_level", "light")
        equipment_anchor_text = row.get("equipment_anchor", "")
        equipment_anchor_list = [item.strip() for item in str(equipment_anchor_text).split(",") if item.strip()]
        first_name = extract_first_name(full_name)

        # Assign sender in round-robin fashion
        sender = Config.get_sender_profile(idx)

        # Get ICP-specific subject line
        custom_subject = get_subject_line_by_icp(icp_match, industry)

        # Get equipment offer based on ICP + equipment context
        equipment_category, software_mention = get_equipment_offer(icp_match, equipment, icp_notes)

        credibility_anchor = build_credibility_anchor(equipment_category)
        cta_label, cta_line = build_cta_line(pain_theme, icp_confidence, followup=False)
        _, cta_line_followup = build_cta_line(pain_theme, icp_confidence, followup=True)
        reinforcement_line = build_reinforcement_line(pain_theme, industry, icp_confidence)

        # Data for template filling
        template_data = {
            "first_name": first_name,
            "industry": industry,
            "personalization_sentence": personalization,
            "company_name": company_name,
            "job_title": job_title_display,
            "signature": sender["signature"],
            "equipment_category": equipment_category,
            "software_mention": software_mention,
            "equipment_anchor": equipment_anchor_text,
            "pain_theme": pain_theme,
            "icp_confidence": icp_confidence,
            "certainty_level": certainty_level,
            "credibility_anchor": credibility_anchor,
            "cta_line": cta_line,
            "cta_line_followup": cta_line_followup,
            "reinforcement_line": reinforcement_line
        }

        personalization_object = {
            "pain_theme": pain_theme,
            "certainty_level": certainty_level,
            "equipment_anchor": equipment_anchor_list,
            "personalization_sentence": personalization
        }
        personalization_object_json = json.dumps(personalization_object, ensure_ascii=True)

        # Email 1 (use custom ICP subject instead of template subject)
        campaign_rows.append({
            "recipient_name": full_name,
            "recipient_email": email_address,
            "recipient_job_title": job_title,
            "company_name": company_name,
            "first_name": first_name,
            "email_sequence": 1,
            "subject": custom_subject,
            "body": fill_template(email_1_body, template_data),
            "personalization_sentence": personalization,
            "personalization_object": personalization_object_json,
            "industry": industry,
            "icp_match": icp_match,
            "role_level": row.get("role_level", "unknown"),
            "icp_confidence": icp_confidence,
            "icp_notes": icp_notes,
            "pain_statement": row.get("pain_statement", ""),
            "equipment": equipment,
            "equipment_anchor": equipment_anchor_text,
            "equipment_category": equipment_category,
            "software_mention": software_mention,
            "pain_theme": pain_theme,
            "certainty_level": certainty_level,
            "cta_label": cta_label,
            "cta_line": cta_line,
            "credibility_anchor": credibility_anchor,
            "sender_name": sender["full_name"],
            "sender_email": sender["email"],
            "sender_title": sender["title"]
        })

        # Email 2 (reuses same personalization, sender, and subject)
        campaign_rows.append({
            "recipient_name": full_name,
            "recipient_email": email_address,
            "recipient_job_title": job_title,
            "company_name": company_name,
            "first_name": first_name,
            "email_sequence": 2,
            "subject": f"Re: {custom_subject}",
            "body": fill_template(email_2_body, template_data),
            "personalization_sentence": personalization,
            "personalization_object": personalization_object_json,
            "industry": industry,
            "icp_match": icp_match,
            "role_level": row.get("role_level", "unknown"),
            "icp_confidence": icp_confidence,
            "icp_notes": icp_notes,
            "pain_statement": row.get("pain_statement", ""),
            "equipment": equipment,
            "equipment_anchor": equipment_anchor_text,
            "equipment_category": equipment_category,
            "software_mention": software_mention,
            "pain_theme": pain_theme,
            "certainty_level": certainty_level,
            "cta_label": cta_label,
            "cta_line": cta_line_followup,
            "credibility_anchor": credibility_anchor,
            "reinforcement_line": reinforcement_line,
            "sender_name": sender["full_name"],
            "sender_email": sender["email"],
            "sender_title": sender["title"]
        })

    # Create output dataframe
    output_df = pd.DataFrame(campaign_rows)

    # Save to CSV
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    output_df.to_csv(output_path, index=False)
    logger.info(f"✓ Saved campaign to: {output_path}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total leads processed: {len(df)}")
    logger.info(f"Campaign rows generated: {len(output_df)} ({len(df)} × 2 emails)")
    logger.info(f"Output file: {output_path}")

    # Show sender distribution
    logger.info("\nSender distribution:")
    sender_counts = output_df[output_df["email_sequence"] == 1]["sender_name"].value_counts()
    for sender, count in sender_counts.items():
        logger.info(f"  - {sender}: {count} leads")

    # Count failures (empty personalization sentences)
    failed = len(df[df["personalization_sentence"] == ""])
    if failed > 0:
        logger.warning(f"\n⚠ {failed} personalization failures - review manually")

    logger.info("\n" + "=" * 60)
    logger.info("NEXT STEPS")
    logger.info("=" * 60)
    logger.info("1. Open the output CSV and review the 'personalization_sentence' column")
    logger.info("2. Look for red flags:")
    logger.info("   - Marketing speak")
    logger.info("   - Phrases like 'I noticed' or 'I saw'")
    logger.info("   - Too generic or too specific")
    logger.info("   - Awkward phrasing")
    logger.info("3. If quality is <90%, iterate on templates/personalization_prompt.txt")
    logger.info("4. Once quality is good, you're ready for Phase 2")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate personalized outreach campaigns"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV file with leads"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to output CSV file for campaigns"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of leads to process (for testing)"
    )

    args = parser.parse_args()

    # Run generation
    generate_campaigns(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
