"""POC system administration: allowlisted account and non-secret integration metadata."""
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

def read_settings():
    from azure.core.exceptions import ResourceNotFoundError
    try:
        row = settings_table().get_entity(partition_key="SYSTEM", row_key="WALLET")
    except ResourceNotFoundError:
        row = {}
    return {
        "google_issuer_id": row.get("google_issuer_id", ""),
        "google_class_id": row.get("google_class_id", ""),
        "apple_team_id": row.get("apple_team_id", ""),
        "apple_pass_type_id": row.get("apple_pass_type_id", ""),
        "platform_label": row.get("platform_label", "Miami CTSI"),
        "google_credentials_configured": bool(os.getenv("RESEARCHPASS_GOOGLE_CREDENTIALS_REF")),
        "apple_certificate_configured": bool(os.getenv("RESEARCHPASS_APPLE_CERTIFICATE_REF")),
        "wallet_generation_enabled": False,
    }

def write_settings(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    allowed = ("google_issuer_id", "google_class_id", "apple_team_id", "apple_pass_type_id", "platform_label")
    row = {"PartitionKey": "SYSTEM", "RowKey": "WALLET"}
    for key in allowed:
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value.strip()) > 160 or any(ord(c) < 32 for c in value):
            raise ValueError(key + " must be text up to 160 characters")
        row[key] = value.strip()
    settings_table().upsert_entity(row, mode="merge")
    return read_settings()
