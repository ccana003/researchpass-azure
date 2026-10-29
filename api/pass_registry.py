"""Synthetic POC Google Wallet link generation audit, not proof of wallet save."""
import os
from datetime import datetime, timezone
from azure.data.tables import TableServiceClient

TABLE = "ResearchPassPassEvents"

def table():
    service = TableServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    service.create_table_if_not_exists(TABLE)
    return service.get_table_client(TABLE)

def record(irb, object_id, issuer_id, study_title):
    table().create_entity({
        "PartitionKey": irb,
        "RowKey": object_id.split(".")[-1],
        "wallet_object_id": object_id,
        "issuer_id": issuer_id,
        "study_title": study_title,
        "platform": "Google Wallet",
        "status": "link_generated",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

def list_events():
    return sorted(({
        "study_id": e["PartitionKey"],
        "study_title": e.get("study_title", ""),
        "wallet_object_id": e.get("wallet_object_id", ""),
        "issuer_id": e.get("issuer_id", ""),
        "issued_at": e.get("created_at", ""),
        "platform": e.get("platform", ""),
        "status": e.get("status", "link_generated"),
    } for e in table().list_entities()), key=lambda e: (e["study_id"], e["issued_at"]), reverse=False)
