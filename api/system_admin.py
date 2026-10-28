"""POC system administration: allowlisted account and non-secret integration metadata."""
import json
import os
from azure.data.tables import TableServiceClient
from local_auth import normalized_email, users_table


def is_admin(user_id):
    email = os.getenv("RESEARCHPASS_ADMIN_EMAIL", "").strip()
    if not email:
        return False
    try:
        record = users_table().get_entity(partition_key="USER", row_key=normalized_email(email))
        return bool(record.get("active")) and record.get("user_id") == user_id
    except Exception:
        return False


def settings_table():
    connection = os.environ["RESEARCHPASS_STORAGE_CONNECTION"]
    service = TableServiceClient.from_connection_string(connection)
    service.create_table_if_not_exists("ResearchPassSystemSettings")
    return service.get_table_client("ResearchPassSystemSettings")


def _google_credentials_configured():
    raw = os.getenv("RESEARCHPASS_GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return False
    try:
        data = json.loads(raw)
        return data.get("type") == "service_account" and bool(data.get("client_email")) and bool(data.get("private_key"))
    except (json.JSONDecodeError, AttributeError):
        return False


def read_settings():
    from azure.core.exceptions import ResourceNotFoundError
    try:
        row = settings_table().get_entity(partition_key="SYSTEM", row_key="WALLET")
    except ResourceNotFoundError:
        row = {}
    google_credentials_configured = _google_credentials_configured()
    google_issuer_id = row.get("google_issuer_id", "")
    google_class_id = row.get("google_class_id", "")
    return {
        "google_issuer_id": google_issuer_id,
        "google_class_id": google_class_id,
        "apple_team_id": row.get("apple_team_id", ""),
        "apple_pass_type_id": row.get("apple_pass_type_id", ""),
        "platform_label": row.get("platform_label", "Miami CTSI"),
        "card_background": row.get("card_background", "#005030"),
        "branding_assets": {name: bool(row.get("asset_" + name)) for name in ("hero", "logo")},
        "google_credentials_configured": google_credentials_configured,
        "apple_certificate_configured": bool(os.getenv("RESEARCHPASS_APPLE_CERTIFICATE_REF")),
        "wallet_generation_enabled": bool(google_credentials_configured and google_issuer_id and google_class_id),
    }


def write_settings(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    allowed = ("google_issuer_id", "google_class_id", "apple_team_id", "apple_pass_type_id", "platform_label", "card_background")
    row = {"PartitionKey": "SYSTEM", "RowKey": "WALLET"}
    for key in allowed:
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value.strip()) > 160 or any(ord(c) < 32 for c in value):
            raise ValueError(key + " must be text up to 160 characters")
        if key == "card_background" and not __import__("re").fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError("card_background must be a six-digit hex color")
        row[key] = value.strip()
    settings_table().upsert_entity(row, mode="merge")
    return read_settings()
