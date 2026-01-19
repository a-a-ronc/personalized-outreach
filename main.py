import argparse
import hashlib
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

# Pain Library for Conventional Material Handling Strategy
# Target: ICP 1 & 3 (pick modules, racking, mezzanines, conventional storage)
PAIN_LIBRARY_CONVENTIONAL = {
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
    "DEFAULT": {
        "unknown": [
            {"theme": "throughput", "statement": "Throughput often tightens where storage and picking exchange materials."},
            {"theme": "integration", "statement": "System handoffs can become the longest tail as operations scale."}
        ]
    }
}

# Pain Library for Semi-Automation & High-Density Strategy
# Target: ICP 2 & 5 (pallet shuttles, VLMs, conveyors, high-density storage)
PAIN_LIBRARY_SEMI_AUTO = {
    "ICP 2": {
        "c_suite": [
            {"theme": "space", "statement": "Dense storage usually delivers faster ROI than full automation, but most WMS systems struggle with shuttle orchestration."},
            {"theme": "integration", "statement": "Automation pilots often stall when controls and WMS coordination becomes the pacing item."}
        ],
        "vp_director": [
            {"theme": "space", "statement": "Pallet shuttles can double capacity without forklift headcount, but staging logic is where most implementations slow down."},
            {"theme": "throughput", "statement": "VLMs tend to bottleneck at the operator interface unless retrieval sequencing ties into your pick logic."}
        ],
        "manager": [
            {"theme": "space", "statement": "Push-back and shuttle systems usually pay back in 18 months, but staging handoffs need design attention upfront."},
            {"theme": "labor", "statement": "Dense storage cuts travel time, but most operations lose the gain if replenishment timing isn't coordinated."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Shuttle controls and WMS handoffs tend to be the first integration friction point in phased rollouts."},
            {"theme": "space", "statement": "High-density layouts force tradeoffs between FIFO access and pallet density that most WMS logic doesn't handle well."}
        ]
    },
    "ICP 5": {
        "c_suite": [
            {"theme": "space", "statement": "High-density storage targets usually come before automation programs are stable."},
            {"theme": "integration", "statement": "Phased automation rollouts often stall when controls coordination becomes the longest tail."}
        ],
        "vp_director": [
            {"theme": "space", "statement": "Density and access tradeoffs tend to sharpen as volumes scale and automation phases overlap."},
            {"theme": "integration", "statement": "Integration planning can slow down phased automation rollouts when controls and WMS timing lags equipment delivery."}
        ],
        "manager": [
            {"theme": "space", "statement": "Storage density can tighten quickly when inbound staging expands ahead of automation deployment."},
            {"theme": "labor", "statement": "Labor coverage tends to get uneven around automated and manual zones during phased rollouts."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Integration between automation and controls tends to surface first in phased rollouts when zone handoffs multiply."},
            {"theme": "space", "statement": "Dense storage layouts usually trade off access time and retrieval sequence unless controls orchestration is designed upfront."}
        ]
    },
    "DEFAULT": {
        "unknown": [
            {"theme": "space", "statement": "Dense storage and access tradeoffs usually surface before automation plans are stable."},
            {"theme": "integration", "statement": "Controls and WMS coordination tends to lag equipment deployment in phased projects."}
        ]
    }
}

# Pain Library for Full Automation Systems Strategy
# Target: ICP 4 & 5 (ASRS, AGV/AMR, sortation, goods-to-person)
PAIN_LIBRARY_FULL_AUTO = {
    "ICP 4": {
        "c_suite": [
            {"theme": "throughput", "statement": "Sortation capacity usually hits theoretical limits before network design does—merge logic and induction timing are the real ceiling."},
            {"theme": "integration", "statement": "Controls orchestration across zones tends to be the longest tail in automated fulfillment expansions."}
        ],
        "vp_director": [
            {"theme": "throughput", "statement": "Peak throughput in sortation systems almost always caps at merge points, not at the sorter itself."},
            {"theme": "integration", "statement": "WMS and controls coordination lags most automation expansions by 3-6 months unless integration planning starts early."}
        ],
        "manager": [
            {"theme": "throughput", "statement": "Induction and merge flow usually constrain sortation throughput more than the equipment spec sheets suggest."},
            {"theme": "labor", "statement": "Labor allocation between induction and outbound tends to swing daily in automated systems without dynamic staffing models."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Controls timing between conveyor zones and sortation merges is almost always the first bottleneck in throughput optimization."},
            {"theme": "throughput", "statement": "Sortation merge logic and accumulation zone sizing usually set the practical throughput ceiling, not the sorter itself."}
        ]
    },
    "ICP 5": {
        "c_suite": [
            {"theme": "integration", "statement": "Automation integration risk often sets the pace for phased upgrades when controls orchestration spans multiple vendors."},
            {"theme": "throughput", "statement": "Automated systems usually cap at zone handoff timing before equipment capacity becomes the bottleneck."}
        ],
        "vp_director": [
            {"theme": "integration", "statement": "Integration planning can slow down phased automation rollouts when AGV traffic and conveyor merge timing need orchestration."},
            {"theme": "throughput", "statement": "Goods-to-person throughput often caps at buffer zone handoffs before robotic pick rates become the constraint."}
        ],
        "manager": [
            {"theme": "integration", "statement": "Zone-to-zone handoffs in automated systems usually create the first throughput ceiling as volumes scale."},
            {"theme": "labor", "statement": "Labor coverage tends to get uneven around automated and manual zones when exception handling workflows aren't defined upfront."}
        ],
        "engineer": [
            {"theme": "integration", "statement": "Integration between automation and controls tends to surface first when zone handoffs multiply across AGV, ASRS, and conveyor systems."},
            {"theme": "throughput", "statement": "Automated material flow usually bottlenecks at merge points and buffer zones before individual equipment hits capacity limits."}
        ]
    },
    "DEFAULT": {
        "unknown": [
            {"theme": "integration", "statement": "Controls orchestration across zones tends to be the longest tail in automated systems."},
            {"theme": "throughput", "statement": "Automated throughput usually caps at zone handoffs before equipment capacity limits."}
        ]
    }
}

# Legacy alias for backward compatibility
PAIN_LIBRARY = PAIN_LIBRARY_CONVENTIONAL

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

CTA_ACTION_VARIANTS = {
    "throughput": [
        "sanity-check the flow",
        "pressure-test the handoff",
        "brainstorm choke-points",
        "review the handoffs"
    ],
    "space": [
        "compare layout options",
        "pressure-test density tradeoffs",
        "map access constraints"
    ],
    "labor": [
        "pressure-test labor assumptions",
        "review labor coverage",
        "sanity-check shift balance"
    ],
    "reconfiguration": [
        "map re-slotting options",
        "review layout adjustments",
        "pressure-test slotting changes"
    ],
    "integration": [
        "walk through handoffs",
        "review system interfaces",
        "pressure-test integration points"
    ]
}

CTA_TEMPLATES = {
    "high": [
        "Can we {action} next week?",
        "Can we {action} this week?",
        "Let's {action} next week."
    ],
    "medium": [
        "If useful, I can {action}.",
        "Happy to {action} if that helps.",
        "If it helps, I can {action}."
    ],
    "low": [
        "If helpful, I can {action}.",
        "Happy to {action} if useful.",
        "If it helps, I can {action}."
    ]
}

CTA_FOLLOWUP_TEMPLATES = {
    "high": [
        "Want me to {action} and send a quick readout?",
        "I can {action} and send a short readout if you'd like.",
        "Happy to {action} and share a {industry} example if useful."
    ],
    "medium": [
        "Happy to {action} and share a short example if helpful.",
        "If useful, I can {action} and send a quick note.",
        "Happy to {action} and share a {industry} example if useful."
    ],
    "low": [
        "If helpful, I can {action} and share a quick example.",
        "Happy to {action} and send a short note if useful.",
        "Happy to {action} and share a {industry} example if it helps."
    ]
}

# Credibility templates with proof elements - strategy specific
CREDIBILITY_TEMPLATES_CONVENTIONAL = [
    "We've designed {equipment_category} in 100+ facilities across food, pharma, and industrial distribution.",
    "We work on {equipment_category} with a focus on reconfiguration speed as client mix shifts.",
    "We implement {equipment_category} and built Warehousr to help you re-slot layouts as SKU velocity changes."
]

CREDIBILITY_TEMPLATES_SEMI_AUTO = [
    "We've deployed {equipment_category} in 40+ facilities where pallet density and FIFO access both matter.",
    "We design {equipment_category} and built DensityPro to handle the staging orchestration most WMS systems skip.",
    "We implement {equipment_category} with partners like Westfalia and Dematic—and fix the controls handoffs that slow most projects."
]

CREDIBILITY_TEMPLATES_FULL_AUTO = [
    "We design {equipment_category} and partner with Lully to handle WMS coordination that most integrators overlook.",
    "We've commissioned {equipment_category} in 30+ fulfillment operations where merge timing determines throughput.",
    "We implement {equipment_category} with OEMs like Honeywell and Intelligrated—our focus is controls orchestration, not just equipment."
]

# Legacy alias for backward compatibility
CREDIBILITY_TEMPLATES = CREDIBILITY_TEMPLATES_CONVENTIONAL

# Subject line templates - strategy specific
SUBJECT_TEMPLATES_CONVENTIONAL = {
    "throughput": [
        "3PL pick module question",
        "Where {industry} flow slows first",
        "Quick thought on {industry} throughput"
    ],
    "reconfiguration": [
        "{industry} slotting lag",
        "Re-slotting timing in {industry}",
        "Layout drift question"
    ],
    "labor": [
        "Replen vs pick coverage in {industry}",
        "Shift balance question",
        "Where labor tightens in {industry}"
    ],
    "integration": [
        "System handoff check",
        "Controls handoff question",
        "Integration handoff note"
    ]
}

SUBJECT_TEMPLATES_SEMI_AUTO = {
    "space": [
        "Pallet shuttle staging question",
        "Dense storage handoff in {industry}",
        "VLM sequencing thought"
    ],
    "integration": [
        "Shuttle + WMS coordination",
        "Controls handoff in {industry}",
        "Phased automation question"
    ],
    "throughput": [
        "VLM retrieval bottleneck",
        "Conveyor merge timing in {industry}",
        "Density vs throughput tradeoff"
    ],
    "labor": [
        "Dense storage labor question",
        "Staging timing in {industry}",
        "Replen coordination thought"
    ]
}

SUBJECT_TEMPLATES_FULL_AUTO = {
    "throughput": [
        "Sortation merge timing",
        "Induction ceiling in {industry}",
        "Where fulfillment caps first"
    ],
    "integration": [
        "Controls orchestration lag",
        "WMS + automation handoff",
        "Zone timing in {industry} sortation"
    ],
    "labor": [
        "Exception handling in automation",
        "Zone staffing in {industry}",
        "Labor allocation question"
    ]
}

# Legacy alias for backward compatibility
SUBJECT_TEMPLATES_BY_THEME = SUBJECT_TEMPLATES_CONVENTIONAL

SUBJECT_TEMPLATES_BY_ICP = {
    "ICP 1": [
        "Pick module flow",
        "Racking layout check"
    ],
    "ICP 2": [
        "Cold storage density",
        "Pallet access tradeoffs"
    ],
    "ICP 3": [
        "Material flow handoffs",
        "Expansion flow check"
    ],
    "ICP 4": [
        "Throughput merge points",
        "Sortation handoff note"
    ],
    "ICP 5": [
        "High-density automation",
        "Phased automation handoffs"
    ]
}

REINFORCEMENT_DETAILS = {
    "throughput": ["merge or induction points", "accumulation zones", "divert logic"],
    "space": ["staging vs storage access", "aisle access tradeoffs", "pallet access timing"],
    "labor": ["picking and replen coverage", "shift handoffs", "replen timing"],
    "reconfiguration": ["slotting changes", "pick path updates", "zone re-balance"],
    "integration": ["controls handoffs", "WMS interface timing", "zone-to-zone signals"]
}

REINFORCEMENT_TEMPLATES = {
    "throughput": [
        "In {industry} flow, throughput {adverb} tightens at {detail}.",
        "In {industry} ops, {detail} is usually where throughput starts to cap.",
        "In {industry} ops, the first pinch is often {detail}."
    ],
    "space": [
        "In {industry} ops, density and access {adverb} collide at {detail}.",
        "In {industry} facilities, {detail} is usually where space tradeoffs surface.",
        "In {industry} ops, space pressure often shows up around {detail}."
    ],
    "labor": [
        "In {industry} ops, labor balance {adverb} tightens around {detail}.",
        "In {industry} ops, {detail} is usually where coverage starts to slip.",
        "In {industry} ops, labor strain often shows up at {detail}."
    ],
    "reconfiguration": [
        "In {industry} ops, layout shifts {adverb} lag at {detail}.",
        "In {industry} ops, {detail} is usually where layout drift shows first.",
        "In {industry} ops, reconfiguration pressure often shows up at {detail}."
    ],
    "integration": [
        "In {industry} ops, handoffs {adverb} drag at {detail}.",
        "In {industry} ops, {detail} is usually where integration slows.",
        "In {industry} ops, integration friction often shows up at {detail}."
    ]
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


def normalize_strategy(value: str, default: str = "conventional") -> str:
    text = normalize_text(value).lower()
    if text in {"conventional", "semi_auto", "full_auto", "hybrid"}:
        return text
    return default


def resolve_email_strategies(row: dict, default_strategy: str) -> tuple[str, str, str]:
    assignment = normalize_strategy(
        row.get("strategy_assignment") or row.get("strategy") or default_strategy,
        default_strategy
    )
    if assignment == "hybrid":
        return assignment, "semi_auto", "full_auto"
    return assignment, assignment, assignment


def deterministic_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    safe_seed = seed or "default"
    digest = hashlib.md5(safe_seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def deterministic_choice(seed: str, options: list[str], salt: str = "") -> str:
    if not options:
        return ""
    index = deterministic_index(f"{seed}|{salt}", len(options))
    return options[index]


def slugify(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text or "")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "default"


def select_variant(seed: str, options: list[str], variant_key: str, salt: str = "") -> tuple[str, str]:
    if not options:
        return f"{variant_key}-0", ""
    index = deterministic_index(f"{seed}|{salt}", len(options))
    variant_id = f"{variant_key}-{index + 1}"
    return variant_id, options[index]


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


def get_pain_library_for_strategy(strategy: str = "conventional") -> dict:
    """Return the appropriate pain library based on campaign strategy"""
    if strategy == "semi_auto":
        return PAIN_LIBRARY_SEMI_AUTO
    elif strategy == "full_auto":
        return PAIN_LIBRARY_FULL_AUTO
    else:
        return PAIN_LIBRARY_CONVENTIONAL


def get_subject_templates_for_strategy(strategy: str = "conventional") -> dict:
    """Return the appropriate subject templates based on campaign strategy"""
    if strategy == "semi_auto":
        return SUBJECT_TEMPLATES_SEMI_AUTO
    elif strategy == "full_auto":
        return SUBJECT_TEMPLATES_FULL_AUTO
    else:
        return SUBJECT_TEMPLATES_CONVENTIONAL


def get_credibility_templates_for_strategy(strategy: str = "conventional") -> list:
    """Return the appropriate credibility templates based on campaign strategy"""
    if strategy == "semi_auto":
        return CREDIBILITY_TEMPLATES_SEMI_AUTO
    elif strategy == "full_auto":
        return CREDIBILITY_TEMPLATES_FULL_AUTO
    else:
        return CREDIBILITY_TEMPLATES_CONVENTIONAL


def select_pain_statement(icp_match: str, role_level: str, pain_theme: str, strategy: str = "conventional") -> str:
    """
    Select pain statement from strategy-specific pain library

    Args:
        icp_match: ICP segment (ICP 1, ICP 2, etc.)
        role_level: Role level (c_suite, vp_director, manager, engineer, unknown)
        pain_theme: Pain theme (throughput, space, labor, etc.)
        strategy: Campaign strategy (conventional, semi_auto, full_auto)

    Returns:
        Pain statement string
    """
    pain_library = get_pain_library_for_strategy(strategy)
    role_entry = pain_library.get(icp_match, {}).get(role_level, [])
    if not role_entry:
        role_entry = pain_library.get("DEFAULT", {}).get("unknown", [])

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


def build_credibility_anchor(equipment_category: str, seed: str, strategy: str = "conventional") -> tuple[str, str]:
    credibility_templates = get_credibility_templates_for_strategy(strategy)
    variant_key = f"cred-{slugify(equipment_category)}"
    variant_id, template = select_variant(
        seed,
        credibility_templates,
        variant_key,
        f"credibility-{equipment_category}"
    )
    return variant_id, template.format(equipment_category=equipment_category)


def build_cta_line(
    pain_theme: str,
    icp_confidence: str,
    industry: str,
    seed: str,
    followup: bool = False
) -> tuple[str, str, str]:
    action_options = CTA_ACTION_VARIANTS.get(pain_theme, CTA_ACTION_VARIANTS["throughput"])
    action_variant_id, action = select_variant(
        seed,
        action_options,
        f"cta-action-{pain_theme}",
        f"cta-action-{pain_theme}"
    )

    confidence_key = icp_confidence if icp_confidence in CTA_TEMPLATES else "low"
    templates = CTA_FOLLOWUP_TEMPLATES if followup else CTA_TEMPLATES
    template_variant_id, template = select_variant(
        seed,
        templates[confidence_key],
        f"cta-template-{pain_theme}-{confidence_key}",
        f"cta-template-{pain_theme}-{confidence_key}-{'f' if followup else 'i'}"
    )

    industry_text = normalize_text(industry) or "operations"
    line = template.format(action=action, industry=industry_text)
    cta_variant_id = f"{action_variant_id}-{template_variant_id}"
    return cta_variant_id, action, line


def build_reinforcement_line(
    pain_theme: str,
    industry: str,
    icp_confidence: str,
    seed: str
) -> tuple[str, str]:
    industry_text = normalize_text(industry) or "operations"
    if icp_confidence == "high":
        adverb = "almost always"
    elif icp_confidence == "medium":
        adverb = "usually"
    else:
        adverb = "can"

    details = REINFORCEMENT_DETAILS.get(pain_theme, REINFORCEMENT_DETAILS["throughput"])
    detail_variant_id, detail = select_variant(seed, details, f"detail-{pain_theme}", f"detail-{pain_theme}")

    templates = REINFORCEMENT_TEMPLATES.get(pain_theme, REINFORCEMENT_TEMPLATES["throughput"])
    template_variant_id, template = select_variant(
        seed,
        templates,
        f"reinforce-{pain_theme}",
        f"reinforce-{pain_theme}"
    )
    variant_id = f"{template_variant_id}-{detail_variant_id}"
    return variant_id, template.format(industry=industry_text, adverb=adverb, detail=detail)


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


def get_subject_line(icp_match: str, pain_theme: str, industry: str, seed: str, strategy: str = "conventional") -> tuple[str, str]:
    """
    Get a deterministic subject line variation based on ICP and pain theme.
    """
    industry_text = normalize_text(industry) or "operations"
    subject_templates = get_subject_templates_for_strategy(strategy)
    theme_templates = subject_templates.get(pain_theme, [])
    icp_templates = SUBJECT_TEMPLATES_BY_ICP.get(icp_match, [])
    fallback = [f"Quick thought on {industry_text} operations"]

    options = theme_templates + icp_templates + fallback
    variant_key = f"subject-{pain_theme}-{slugify(icp_match)}"
    variant_id, selected = select_variant(seed, options, variant_key, "subject")
    return variant_id, selected.replace("{industry}", industry_text)


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


def prepare_personalization_controls(df: pd.DataFrame, strategy: str = "conventional") -> pd.DataFrame:
    role_levels = []
    icp_confidences = []
    certainty_levels = []
    pain_themes = []
    pain_statements = []
    equipment_anchors = []
    strategy_assignments = []
    strategy_email_1 = []
    strategy_email_2 = []

    for _, row in df.iterrows():
        job_title = normalize_text(row.get("Job title", ""))
        industry = normalize_text(row.get("Industry", ""))
        icp_match = normalize_text(row.get("ICP Match", ""))
        notes = normalize_text(row.get("Notes", ""))
        equipment = normalize_text(row.get("Equipment", ""))

        role_level = classify_role_level(job_title)
        anchors = extract_equipment_anchors(equipment, notes)
        pain_theme = infer_pain_theme(icp_match, role_level, equipment, notes)
        assignment, email_1_strategy, email_2_strategy = resolve_email_strategies(row, strategy)
        pain_statement = select_pain_statement(icp_match, role_level, pain_theme, email_1_strategy)
        icp_confidence = compute_icp_confidence(icp_match, industry, role_level, anchors)
        certainty_level = confidence_to_certainty(icp_confidence)

        role_levels.append(role_level)
        icp_confidences.append(icp_confidence)
        certainty_levels.append(certainty_level)
        pain_themes.append(pain_theme)
        pain_statements.append(pain_statement)
        equipment_anchors.append(", ".join(anchors))
        strategy_assignments.append(assignment)
        strategy_email_1.append(email_1_strategy)
        strategy_email_2.append(email_2_strategy)

    df["role_level"] = role_levels
    df["icp_confidence"] = icp_confidences
    df["certainty_level"] = certainty_levels
    df["pain_theme"] = pain_themes
    df["pain_statement"] = pain_statements
    df["equipment_anchor"] = equipment_anchors
    df["strategy_assignment"] = strategy_assignments
    df["strategy_email_1"] = strategy_email_1
    df["strategy_email_2"] = strategy_email_2

    return df


def generate_campaigns(input_path: str, output_path: str, limit: int = None, raise_on_error: bool = False, strategy: str = "conventional"):
    """
    Main function to generate personalized email campaigns

    Args:
        input_path: Path to input CSV with leads
        output_path: Path to output CSV with campaigns
        limit: Optional limit on number of leads to process
        raise_on_error: Raise exceptions instead of exiting (useful for web apps)
        strategy: Campaign strategy (conventional, semi_auto, full_auto)
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
    logger.info(f"Using campaign strategy: {strategy}")
    df = prepare_personalization_controls(df, strategy)

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
        assignment, email_1_strategy, email_2_strategy = resolve_email_strategies(row, strategy)

        # Assign sender in round-robin fashion
        sender = Config.get_sender_profile(idx)

        base_seed = f"{company_name}|{sender['email']}"
        seed_email_1 = f"{base_seed}|1"
        seed_email_2 = f"{base_seed}|2"
        personalization_hash_email_1 = hashlib.md5(seed_email_1.encode("utf-8")).hexdigest()
        personalization_hash_email_2 = hashlib.md5(seed_email_2.encode("utf-8")).hexdigest()

        # Get subject line variant
        subject_variant_id, custom_subject = get_subject_line(
            icp_match,
            pain_theme,
            industry,
            seed_email_1,
            email_1_strategy
        )

        # Get equipment offer based on ICP + equipment context
        equipment_category, software_mention = get_equipment_offer(icp_match, equipment, icp_notes)

        credibility_variant_id, credibility_anchor = build_credibility_anchor(
            equipment_category,
            seed_email_1,
            email_1_strategy
        )
        credibility_variant_id_followup, credibility_anchor_followup = build_credibility_anchor(
            equipment_category,
            seed_email_2,
            email_2_strategy
        )
        cta_variant_id, cta_label, cta_line = build_cta_line(
            pain_theme,
            icp_confidence,
            industry,
            seed_email_1,
            followup=False
        )
        cta_variant_id_followup, _, cta_line_followup = build_cta_line(
            pain_theme,
            icp_confidence,
            industry,
            seed_email_2,
            followup=True
        )
        reinforcement_variant_id, reinforcement_line = build_reinforcement_line(
            pain_theme,
            industry,
            icp_confidence,
            seed_email_2
        )

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
            "reinforcement_line": reinforcement_line,
            "subject_variant_id": subject_variant_id,
            "cta_variant_id": cta_variant_id,
            "cta_variant_id_followup": cta_variant_id_followup,
            "credibility_variant_id": credibility_variant_id,
            "reinforcement_variant_id": reinforcement_variant_id
        }

        personalization_object_email_1 = {
            "pain_theme": pain_theme,
            "certainty_level": certainty_level,
            "equipment_anchor": equipment_anchor_list,
            "personalization_sentence": personalization,
            "subject_variant_id": subject_variant_id,
            "cta_variant_id": cta_variant_id,
            "credibility_variant_id": credibility_variant_id,
            "reinforcement_variant_id": "",
            "personalization_hash": personalization_hash_email_1
        }
        personalization_object_email_2 = {
            "pain_theme": pain_theme,
            "certainty_level": certainty_level,
            "equipment_anchor": equipment_anchor_list,
            "personalization_sentence": personalization,
            "subject_variant_id": subject_variant_id,
            "cta_variant_id": cta_variant_id_followup,
            "credibility_variant_id": credibility_variant_id,
            "reinforcement_variant_id": reinforcement_variant_id,
            "personalization_hash": personalization_hash_email_2
        }
        personalization_object_json_email_1 = json.dumps(
            personalization_object_email_1,
            ensure_ascii=True
        )
        personalization_object_json_email_2 = json.dumps(
            personalization_object_email_2,
            ensure_ascii=True
        )

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
            "personalization_object": personalization_object_json_email_1,
            "personalization_hash": personalization_hash_email_1,
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
            "cta_variant_id": cta_variant_id,
            "subject_variant_id": subject_variant_id,
            "credibility_anchor": credibility_anchor,
            "credibility_variant_id": credibility_variant_id,
            "strategy_assignment": assignment,
            "strategy_email_1": email_1_strategy,
            "strategy_email_2": email_2_strategy,
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
            "personalization_object": personalization_object_json_email_2,
            "personalization_hash": personalization_hash_email_2,
            "industry": industry,
            "icp_match": icp_match,
            "role_level": row.get("role_level", "unknown"),
            "icp_confidence": icp_confidence,
            "icp_notes": icp_notes,
            "pain_statement": select_pain_statement(
                icp_match,
                row.get("role_level", "unknown"),
                pain_theme,
                email_2_strategy
            ),
            "equipment": equipment,
            "equipment_anchor": equipment_anchor_text,
            "equipment_category": equipment_category,
            "software_mention": software_mention,
            "pain_theme": pain_theme,
            "certainty_level": certainty_level,
            "cta_label": cta_label,
            "cta_line": cta_line_followup,
            "cta_variant_id": cta_variant_id_followup,
            "subject_variant_id": subject_variant_id,
            "credibility_anchor": credibility_anchor_followup,
            "credibility_variant_id": credibility_variant_id_followup,
            "reinforcement_line": reinforcement_line,
            "reinforcement_variant_id": reinforcement_variant_id,
            "strategy_assignment": assignment,
            "strategy_email_1": email_1_strategy,
            "strategy_email_2": email_2_strategy,
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
