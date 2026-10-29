"""IBIS-to-ResearchPass integration boundary.

IT can POST canonical study data here after retrieving it from IBIS.
This adapter deliberately makes no assumptions about IBIS API endpoints.
"""
import os
import re
from datetime import datetime, timezone
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError
from studies import normalize_irb

def _text(value, field, maximum=250, required=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value.strip()) > maximum or (required and not value.strip()):
        raise ValueError(field + " must be text" + (" and is required" if required else "") + " (max " + str(maximum) + " characters)")
    return value.strip()

def _email(value, field):
    value = _text(value, field)
    if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError(field + " must be a valid email")
    return value

def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    irb = _text(payload.get("protocol_number"), "protocol_number", 64, True)
    normalize_irb(irb)
    team = payload.get("study_team", [])
    if not isinstance(team, list) or len(team) > 500:
        raise ValueError("study_team must be a list of up to 500 members")
    members = []
    for i, person in enumerate(team):
        if not isinstance(person, dict):
            raise ValueError("study_team entries must be objects")
        members.append({
            "name": _text(person.get("name"), "study_team.name", 150, True),
            "email": _email(person.get("email"), "study_team.email"),
            "role": _text(person.get("role"), "study_team.role", 100),
            "external_person_id": _text(person.get("external_person_id"), "study_team.external_person_id", 100),
            "external_id_type": _text(person.get("external_id_type"), "study_team.external_id_type", 50)
        })
    return {
        "protocol_number": irb,
        "study_title": _text(payload.get("study_title"), "study_title", 250, True),
        "principal_investigator": _text(payload.get("principal_investigator"), "principal_investigator", 250),
        "contact_email": _email(payload.get("contact_email"), "contact_email"),
        "contact_phone": _text(payload.get("contact_phone"), "contact_phone", 80),
        "study_team": members
    }

def _table(name):
    service = TableServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    service.create_table_if_not_exists(name)
    return service.get_table_client(name)

def upsert(payload):
    data = validate(payload)
    key = normalize_irb(data["protocol_number"])
    studies = _table("ResearchPassStudies")
    try:
        entity = studies.get_entity(partition_key="STUDY", row_key=key)
    except ResourceNotFoundError:
        # An IBIS sync is not an authorization to create an active issuer-owned study.
        raise LookupError("Study is not registered in ResearchPass; register it before syncing")
    entity.update({
        "study_title": data["study_title"],
        "pi_name": data["principal_investigator"],

        "ibis_last_synced_at": datetime.now(timezone.utc).isoformat(),
        "ibis_sync_status": "synced"
    })
    if not entity.get("contact_override", False):
        entity["contact_email"] = data["contact_email"]
        entity["contact_phone"] = data["contact_phone"]
    studies.update_entity(entity, mode="merge")
    # Keep IBIS study-team roster separate from ResearchPass access memberships.
    roster = _table("ResearchPassIBISStudyTeam")
    roster.upsert_entity({
        "PartitionKey": "STUDY", "RowKey": key,
        "study_team_json": __import__("json").dumps(data["study_team"]),
        "synced_at": entity["ibis_last_synced_at"]
    })
    return {"protocol_number": data["protocol_number"], "status": "synced",
            "study_team_count": len(data["study_team"]), "access_granted": False,
            "synced_at": entity["ibis_last_synced_at"]}
