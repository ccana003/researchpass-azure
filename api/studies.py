"""ResearchPass study storage and validation."""
import os
import re
from datetime import datetime, timezone
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError

TABLE_NAME = "ResearchPassStudies"

class DuplicateStudyError(Exception):
    pass

def normalize_irb(value):
    if not isinstance(value, str):
        raise ValueError("irb_number must be a string")
    normalized = re.sub(r"[^A-Z0-9]", "", value.strip().upper())
    if not 3 <= len(normalized) <= 64:
        raise ValueError("irb_number must contain 3 to 64 letters or digits")
    return normalized

def create_study(irb_number, study_title, created_by):
    irb_key = normalize_irb(irb_number)
    if not isinstance(study_title, str) or not 1 <= len(study_title.strip()) <= 250:
        raise ValueError("study_title must contain 1 to 250 characters")
    connection = os.environ.get("RESEARCHPASS_STORAGE_CONNECTION")
    if not connection:
        raise RuntimeError("Study storage is not configured")
    client = TableServiceClient.from_connection_string(connection).get_table_client(TABLE_NAME)
    entity = {
        "PartitionKey": "STUDY",
        "RowKey": irb_key,
        "irb_number": irb_number.strip(),
        "study_title": study_title.strip(),
        "study_status": "registered",
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        client.create_entity(entity=entity)
    except ResourceExistsError as exc:
        raise DuplicateStudyError("A study with this IRB number is already registered") from exc
    return {"irb_number": entity["irb_number"], "study_title": entity["study_title"], "study_status": entity["study_status"]}
