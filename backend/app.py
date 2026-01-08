from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, abort, jsonify, request
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = BASE_DIR / "data" / "campaigns.json"
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


def load_json() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {"campaigns": []}


def save_json(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def relative_path(path: Path) -> str:
    return path.relative_to(BASE_DIR).as_posix()


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
        payload = request.json or {}
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
        payload = request.json or {}
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

    payload = request.json or {}
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

    payload = request.json or {}
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

    payload = request.json or {}
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
                "name": row.get("Full name", ""),
                "email": row.get("Email address", ""),
                "company": row.get("Company", ""),
                "title": row.get("Job title", ""),
                "industry": row.get("Industry", "")
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
                "sequence": int(row.get("email_sequence", 1)),
                "subject": row.get("subject", ""),
                "body": row.get("body", ""),
                "sender": row.get("sender_name", ""),
                "sender_email": row.get("sender_email", ""),
                "recipient": row.get("recipient_email", "")
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
