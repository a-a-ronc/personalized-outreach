from __future__ import annotations

import os
import socket
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, abort, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "webapp" / "templates"
STATIC_DIR = BASE_DIR / "webapp" / "static"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
ALLOWED_EXTENSIONS = {".csv"}

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from main import generate_campaigns  # noqa: E402

app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def build_default_output_name() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"campaigns_{timestamp}.csv"


def sanitize_output_name(raw_name: str, default_name: str) -> str:
    cleaned = secure_filename(raw_name.strip()) if raw_name else ""
    if not cleaned:
        cleaned = default_name
    if not cleaned.lower().endswith(".csv"):
        cleaned += ".csv"
    return cleaned


def build_summary(output_path: Path) -> dict:
    summary = {"total_rows": 0, "lead_count": None, "email_1_count": None}
    if not output_path.exists():
        return summary

    df = pd.read_csv(output_path)
    summary["total_rows"] = int(len(df))

    if "recipient_email" in df.columns:
        summary["lead_count"] = int(df["recipient_email"].nunique())
    elif "company_name" in df.columns:
        summary["lead_count"] = int(df["company_name"].nunique())

    if "email_sequence" in df.columns:
        summary["email_1_count"] = int((df["email_sequence"] == 1).sum())

    return summary


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

    for candidate in (5000, 5001, 5002, 5050, 5100, 8000):
        if is_port_available(candidate):
            return candidate

    return 0


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    result = None
    default_output_name = build_default_output_name()

    if request.method == "POST":
        file = request.files.get("csv_file")
        limit_raw = request.form.get("limit", "").strip()
        output_raw = request.form.get("output_filename", "")

        if not file or file.filename.strip() == "":
            error = "Please choose a CSV file to upload."
        elif not allowed_file(file.filename):
            error = "Only .csv files are supported."
        else:
            try:
                limit = int(limit_raw) if limit_raw else None
                if limit is not None and limit <= 0:
                    raise ValueError("Limit must be a positive number.")

                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

                safe_upload_name = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                upload_path = UPLOAD_DIR / f"{timestamp}_{safe_upload_name}"
                file.save(upload_path)

                output_name = sanitize_output_name(output_raw, default_output_name)
                output_path = OUTPUT_DIR / output_name

                generate_campaigns(
                    str(upload_path),
                    str(output_path),
                    limit=limit,
                    raise_on_error=True,
                )

                summary = build_summary(output_path)
                result = {
                    "output_name": output_name,
                    "download_url": f"/download/{output_name}",
                    "summary": summary,
                }
            except Exception as exc:
                error = str(exc)

    return render_template(
        "index.html",
        error=error,
        result=result,
        default_output_name=default_output_name,
    )


@app.route("/download/<path:filename>")
def download(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        abort(404)

    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        abort(404)

    return send_from_directory(OUTPUT_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    host = "127.0.0.1"
    port = choose_port()
    try:
        app.run(host=host, port=port)
    except OSError as exc:
        if port != 0:
            port = 0
            app.run(host=host, port=port)
        else:
            raise exc
