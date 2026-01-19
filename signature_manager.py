import re
import base64
from pathlib import Path
from bs4 import BeautifulSoup
import uuid
from lead_registry import get_connection, utc_now


def extract_outlook_signature_windows():
    """Extract Outlook signatures from Windows AppData."""
    signature_path = Path.home() / "AppData/Roaming/Microsoft/Signatures"
    signatures = []

    if not signature_path.exists():
        return signatures

    for sig_file in signature_path.glob("*.htm"):
        try:
            with open(sig_file, 'r', encoding='utf-8', errors='ignore') as f:
                html = f.read()

                # Embed images as base64
                html_with_images = embed_images_as_base64(html, sig_file.parent)

                signatures.append({
                    'name': sig_file.stem,
                    'html': html_with_images,
                    'plain_text': extract_text_from_html(html)
                })
        except Exception as e:
            print(f"Error reading signature {sig_file}: {e}")
            continue

    return signatures


def extract_text_from_html(html):
    """Extract plain text version from HTML signature."""
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator='\n', strip=True)


def embed_images_as_base64(html, signature_dir):
    """Convert linked images to base64 embedded images."""
    soup = BeautifulSoup(html, 'html.parser')

    for img in soup.find_all('img'):
        src = img.get('src')
        if not src or src.startswith('data:') or src.startswith('http'):
            continue

        # Try to find the image file
        img_path = signature_dir / src
        if not img_path.exists():
            # Try with different extensions
            for ext in ['.png', '.jpg', '.jpeg', '.gif']:
                alt_path = signature_dir / (src.rsplit('.', 1)[0] + ext)
                if alt_path.exists():
                    img_path = alt_path
                    break

        if img_path.exists():
            try:
                with open(img_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()
                    # Detect image type
                    ext = img_path.suffix.lower()
                    mime_type = {
                        '.png': 'image/png',
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif'
                    }.get(ext, 'image/png')

                    img['src'] = f"data:{mime_type};base64,{img_data}"
            except Exception as e:
                print(f"Error embedding image {img_path}: {e}")

    return str(soup)


def save_signature(name, html_content, plain_text_content, user_email="", is_default=False):
    """Save signature to database."""
    signature_id = str(uuid.uuid4())
    now = utc_now()

    with get_connection() as conn:
        # If setting as default, unset other defaults
        if is_default:
            conn.execute("UPDATE signatures SET is_default = 0")

        conn.execute("""
            INSERT INTO signatures (id, user_email, name, html_content, plain_text_content, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (signature_id, user_email, name, html_content, plain_text_content, 1 if is_default else 0, now, now))

    return signature_id


def get_signature(signature_id):
    """Get signature by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM signatures WHERE id = ?", (signature_id,)).fetchone()
    return dict(row) if row else None


def get_all_signatures():
    """Get all signatures."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM signatures ORDER BY is_default DESC, created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_default_signature():
    """Get the default signature."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM signatures WHERE is_default = 1").fetchone()
    return dict(row) if row else None


def update_signature(signature_id, name=None, html_content=None, plain_text_content=None, is_default=None):
    """Update signature."""
    now = utc_now()

    with get_connection() as conn:
        if is_default:
            conn.execute("UPDATE signatures SET is_default = 0")

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if html_content is not None:
            updates.append("html_content = ?")
            params.append(html_content)
        if plain_text_content is not None:
            updates.append("plain_text_content = ?")
            params.append(plain_text_content)
        if is_default is not None:
            updates.append("is_default = ?")
            params.append(1 if is_default else 0)

        updates.append("updated_at = ?")
        params.append(now)
        params.append(signature_id)

        conn.execute(f"UPDATE signatures SET {', '.join(updates)} WHERE id = ?", params)


def delete_signature(signature_id):
    """Delete signature."""
    with get_connection() as conn:
        conn.execute("DELETE FROM signatures WHERE id = ?", (signature_id,))


def import_outlook_signatures():
    """Import all Outlook signatures and save to database."""
    signatures = extract_outlook_signature_windows()
    imported_ids = []

    for sig in signatures:
        signature_id = save_signature(
            name=sig['name'],
            html_content=sig['html'],
            plain_text_content=sig['plain_text'],
            is_default=len(imported_ids) == 0  # First signature is default
        )
        imported_ids.append(signature_id)

    return imported_ids
