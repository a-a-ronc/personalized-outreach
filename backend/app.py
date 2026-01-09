from __future__ import annotations

import json
import os
import socket
import sys
import uuid
import logging
import hashlib
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

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

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


def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,OPTIONS"
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


@app.route("/api/campaigns", methods=["GET", "POST"])
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
        generate_campaigns(
            str(input_path),
            str(output_path),
            limit=int(limit) if limit else None,
            raise_on_error=True,
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
    sender_list = []
    for profile in Config.SENDER_PROFILES:
        sender_list.append(
            {
                "name": profile["full_name"],
                "email": profile["email"],
                "title": profile["title"],
                "status": "Connected",
                "sent_today": 0,
                "pending": 0
            }
        )
    return jsonify(sender_list)


if __name__ == "__main__":
    ensure_seed_data()
    host = "127.0.0.1"
    port = choose_port()
    try:
        app.run(host=host, port=port)
    except OSError as exc:
        if port != 0:
            app.run(host=host, port=0)
        else:
            raise exc
