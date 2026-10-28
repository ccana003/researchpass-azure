"""POC-only local accounts: invitation-gated registration and signed sessions."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

import jwt
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.data.tables import TableServiceClient

USERS_TABLE = "ResearchPassUsers"
ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60

class LocalAuthError(Exception):
    pass

class LocalAuthNotConfigured(Exception):
    pass

def config():
    connection = os.getenv("RESEARCHPASS_STORAGE_CONNECTION", "")
    signing = os.getenv("RESEARCHPASS_SESSION_SECRET", "")
    invite = os.getenv("RESEARCHPASS_INVITE_CODE", "")
    if not connection or len(signing) < 32 or len(invite) < 20:
        raise LocalAuthNotConfigured("POC account settings are not configured")
    return connection, signing, invite

def users_table():
    connection, _, _ = config()
    service = TableServiceClient.from_connection_string(connection)
    service.create_table_if_not_exists(USERS_TABLE)
    return service.get_table_client(USERS_TABLE)

def normalized_email(email):
    if not isinstance(email, str):
        raise ValueError("Valid email is required")
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Valid email is required")
    return email

def password_hash(password, salt=None):
    if not isinstance(password, str) or len(password) < 14 or len(password) > 128:
        raise ValueError("Password must be 14 to 128 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()

def register(email, password, invite_code):
    _, _, expected = config()
    if not isinstance(invite_code, str) or not hmac.compare_digest(invite_code, expected):
        raise LocalAuthError("Invalid invitation code")
    email = normalized_email(email)
    salt, digest = password_hash(password)
    user_id = str(uuid.uuid4())
    try:
        users_table().create_entity({
            "PartitionKey": "USER",
            "RowKey": email,
            "user_id": user_id,
            "salt": salt,
            "password_digest": digest,
            "active": True,
            "created_at": int(time.time())
        })
    except ResourceExistsError as exc:
        raise LocalAuthError("An account with this email already exists") from exc
    return {"email": email, "user_id": user_id}

def login(email, password):
    _, signing, _ = config()
    email = normalized_email(email)
    try:
        user = users_table().get_entity(partition_key="USER", row_key=email)
    except ResourceNotFoundError:
        raise LocalAuthError("Invalid email or password") from None
    if not isinstance(password, str) or not user.get("active"):
        raise LocalAuthError("Invalid email or password")
    try:
        salt = base64.b64decode(user["salt"], validate=True)
        stored = base64.b64decode(user["password_digest"], validate=True)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    except (ValueError, KeyError):
        raise LocalAuthError("Invalid email or password") from None
    if not hmac.compare_digest(stored, actual):
        raise LocalAuthError("Invalid email or password")
    now = int(time.time())
    token = jwt.encode({"sub": user["user_id"], "iat": now, "exp": now + SESSION_SECONDS, "iss": "researchpass-poc", "aud": "researchpass-api"}, signing, algorithm="HS256")
    return {"access_token": token, "token_type": "Bearer", "expires_in": SESSION_SECONDS}

def authenticate(req):
    _, signing, _ = config()
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise LocalAuthError("Sign in is required")
    try:
        claims = jwt.decode(header[7:].strip(), signing, algorithms=["HS256"], audience="researchpass-api", issuer="researchpass-poc", options={"require": ["sub", "iat", "exp"]})
        return claims["sub"]
    except jwt.PyJWTError:
        raise LocalAuthError("Invalid or expired session") from None
