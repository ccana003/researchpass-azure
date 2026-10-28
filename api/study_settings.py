"""Owner-managed, per-study ResearchPass wallet display settings (POC)."""
import os
from azure.data.tables import TableServiceClient
from studies import normalize_irb

FIELDS = ("pi_name", "contact_email", "contact_phone", "display_name")
def client():
    connection = os.environ.get("RESEARCHPASS_STORAGE_CONNECTION")
    if not connection:
        raise RuntimeError("Study storage is not configured")
    return TableServiceClient.from_connection_string(connection).get_table_client("ResearchPassStudies")

def get_settings(irb_number):
    entity = client().get_entity(partition_key="STUDY", row_key=normalize_irb(irb_number))
    return {
        "irb_number": entity["irb_number"],
        "study_title": entity["study_title"],
        "display_name": entity.get("display_name", entity["study_title"]),
        "pi_name": entity.get("pi_name", ""),
        "contact_email": entity.get("contact_email", ""),
        "contact_phone": entity.get("contact_phone", ""),
        "require_start_date": entity.get("require_start_date", False),
        "require_end_date": entity.get("require_end_date", False),
    }

def save_settings(irb_number, payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    entity = client().get_entity(partition_key="STUDY", row_key=normalize_irb(irb_number))
    for field in FIELDS:
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > 250:
            raise ValueError(field + " must be text of at most 250 characters")
        entity[field] = value.strip()
    for field in ("require_start_date", "require_end_date"):
        value = payload.get(field, False)
        if not isinstance(value, bool):
            raise ValueError(field + " must be true or false")
        entity[field] = value
    if entity["contact_email"] and ("@" not in entity["contact_email"] or " " in entity["contact_email"]):
        raise ValueError("contact_email must be a valid email address")
    client().update_entity(entity=entity, mode="merge")
    return get_settings(irb_number)
