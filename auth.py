"""
Authentication Module

Handles user registration, login, and session management.
Simple authentication for internal tool - single admin user initially.
"""

import os
import bcrypt
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import request, jsonify
import jwt

from lead_registry import get_connection, utc_now

logger = logging.getLogger(__name__)

# JWT secret key from environment or generate one
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def init_auth_tables():
    """Initialize authentication tables."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                role TEXT DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                login_count INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """)

        logger.info("Auth tables initialized")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    return password_hash.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def create_user(username: str, email: str, password: str, full_name: str = None, role: str = "user") -> dict:
    """
    Create a new user account.

    Args:
        username: Unique username
        email: Unique email address
        password: Plain text password (will be hashed)
        full_name: Optional full name
        role: User role (user, admin)

    Returns:
        dict with success status and user info or error
    """
    # Validate inputs
    if not username or len(username) < 3:
        return {"success": False, "error": "Username must be at least 3 characters"}

    if not email or "@" not in email:
        return {"success": False, "error": "Valid email required"}

    if not password or len(password) < 8:
        return {"success": False, "error": "Password must be at least 8 characters"}

    # Hash password
    password_hash = hash_password(password)
    now = utc_now()

    try:
        with get_connection() as conn:
            # Check if user already exists
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email)
            ).fetchone()

            if existing:
                return {"success": False, "error": "Username or email already exists"}

            # Insert new user
            cursor = conn.execute("""
                INSERT INTO users (username, email, password_hash, full_name, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, email, password_hash, full_name, role, now))

            user_id = cursor.lastrowid

            logger.info(f"Created user: {username} ({email})")

            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "full_name": full_name,
                    "role": role
                }
            }

    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        return {"success": False, "error": str(e)}


def authenticate_user(username_or_email: str, password: str) -> dict:
    """
    Authenticate a user with username/email and password.

    Args:
        username_or_email: Username or email address
        password: Plain text password

    Returns:
        dict with success status, user info, and JWT token
    """
    try:
        with get_connection() as conn:
            # Find user by username or email
            user = conn.execute("""
                SELECT id, username, email, password_hash, full_name, role, is_active
                FROM users
                WHERE username = ? OR email = ?
            """, (username_or_email, username_or_email)).fetchone()

            if not user:
                return {"success": False, "error": "Invalid credentials"}

            if not user["is_active"]:
                return {"success": False, "error": "Account is disabled"}

            # Verify password
            if not verify_password(password, user["password_hash"]):
                return {"success": False, "error": "Invalid credentials"}

            # Update last login
            now = utc_now()
            conn.execute("""
                UPDATE users
                SET last_login_at = ?, login_count = login_count + 1
                WHERE id = ?
            """, (now, user["id"]))

            # Generate JWT token
            token = generate_jwt_token(user["id"], user["username"], user["role"])

            logger.info(f"User logged in: {user['username']}")

            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "role": user["role"]
                },
                "token": token
            }

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return {"success": False, "error": "Authentication failed"}


def generate_jwt_token(user_id: int, username: str, role: str) -> str:
    """Generate a JWT token for a user."""
    expiration = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)

    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": expiration,
        "iat": datetime.now(timezone.utc)
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def verify_jwt_token(token: str) -> dict:
    """
    Verify and decode a JWT token.

    Returns:
        dict with user info if valid, or None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        return None


def get_current_user_from_token(token: str) -> dict:
    """Get current user info from JWT token."""
    payload = verify_jwt_token(token)
    if not payload:
        return None

    try:
        with get_connection() as conn:
            user = conn.execute("""
                SELECT id, username, email, full_name, role, is_active
                FROM users
                WHERE id = ?
            """, (payload["user_id"],)).fetchone()

            if not user or not user["is_active"]:
                return None

            return dict(user)
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        return None


def require_auth(f):
    """Decorator to require authentication for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Authentication required"}), 401

        # Extract token (format: "Bearer <token>")
        try:
            token = auth_header.split(" ")[1] if " " in auth_header else auth_header
        except IndexError:
            return jsonify({"error": "Invalid authorization header"}), 401

        # Verify token
        user = get_current_user_from_token(token)

        if not user:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Add user to request context
        request.current_user = user

        return f(*args, **kwargs)

    return decorated_function


def require_admin(f):
    """Decorator to require admin role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First require authentication
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Authentication required"}), 401

        try:
            token = auth_header.split(" ")[1] if " " in auth_header else auth_header
        except IndexError:
            return jsonify({"error": "Invalid authorization header"}), 401

        user = get_current_user_from_token(token)

        if not user:
            return jsonify({"error": "Invalid or expired token"}), 401

        if user["role"] != "admin":
            return jsonify({"error": "Admin access required"}), 403

        request.current_user = user

        return f(*args, **kwargs)

    return decorated_function


def get_all_users() -> list:
    """Get all users (admin only)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, username, email, full_name, role, is_active,
                   created_at, last_login_at, login_count
            FROM users
            ORDER BY created_at DESC
        """).fetchall()

    return [dict(row) for row in rows]


def update_user(user_id: int, **updates) -> dict:
    """Update user information (admin only)."""
    allowed_fields = ["full_name", "email", "role", "is_active"]

    # Filter allowed fields
    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        return {"success": False, "error": "No valid fields to update"}

    # Build UPDATE query
    set_clause = ", ".join([f"{field} = ?" for field in valid_updates.keys()])
    values = list(valid_updates.values()) + [user_id]

    try:
        with get_connection() as conn:
            conn.execute(f"""
                UPDATE users
                SET {set_clause}
                WHERE id = ?
            """, values)

            logger.info(f"Updated user {user_id}: {valid_updates}")

            return {"success": True}

    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        return {"success": False, "error": str(e)}


def change_password(user_id: int, old_password: str, new_password: str) -> dict:
    """Change user password."""
    if len(new_password) < 8:
        return {"success": False, "error": "Password must be at least 8 characters"}

    try:
        with get_connection() as conn:
            # Get current password hash
            user = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()

            if not user:
                return {"success": False, "error": "User not found"}

            # Verify old password
            if not verify_password(old_password, user["password_hash"]):
                return {"success": False, "error": "Current password is incorrect"}

            # Hash new password
            new_hash = hash_password(new_password)

            # Update password
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, user_id)
            )

            logger.info(f"Password changed for user {user_id}")

            return {"success": True}

    except Exception as e:
        logger.error(f"Failed to change password: {e}")
        return {"success": False, "error": "Failed to change password"}


def create_default_admin():
    """
    Create default admin user if no users exist.
    Username: admin
    Password: Read from ADMIN_PASSWORD env var or default to 'admin123'
    """
    try:
        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]

            if count > 0:
                logger.info("Users already exist, skipping default admin creation")
                return

        # Get admin password from environment or use default
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

        result = create_user(
            username="admin",
            email="admin@example.com",
            password=admin_password,
            full_name="System Administrator",
            role="admin"
        )

        if result["success"]:
            logger.warning(f"Created default admin user - USERNAME: admin, PASSWORD: {admin_password}")
            logger.warning("SECURITY: Change the admin password immediately!")

    except Exception as e:
        logger.error(f"Failed to create default admin: {e}")
