"""Admin-only, preview-first institutional XML study import."""
import hashlib
import io
import json
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient
from studies import normalize_irb

MAX_BYTES = 8 * 1024 * 1024
FIELDS = {
    "BriefTitle": ("study_title", 250),
    "PIName": ("pi_name", 250),
    "StudyContact": ("study_contact", 250),
    "StudyContactEmail": ("contact_email", 250),
    "StudyContactPhone": ("contact_phone", 80),
    "VelosCurrentStudyStatus": ("institutional_status", 150),
}

def parse_xml(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError("XML file must be between 1 byte and 8 MB")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DOCTYPE and entity declarations are not permitted")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Invalid XML document") from exc
    rows = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() == "row"]
    if not rows:
        raise ValueError("No row elements found in XML")
    if len(rows) > 20000:
        raise ValueError("XML contains too many study rows")
    studies = {}
    errors = []
    for index, row in enumerate(rows, 1):
        fields = {node.tag.rsplit("}", 1)[-1]: (node.text or "").strip() for node in row}
        irb = fields.get("EprostNbr", "")
        title = fields.get("BriefTitle", "")
        if not irb or not title:
            errors.append("Row %d: EprostNbr and BriefTitle are required" % index)
            continue
        try:
            key = normalize_irb(irb)
        except ValueError:
            errors.append("Row %d: invalid EprostNbr" % index)
            continue
        if key in studies:
            errors.append("Row %d: duplicate EprostNbr %s" % (index, irb))
            continue
        record = {"irb_number": irb, "institutional_contact_email": fields.get("StudyContactEmail", "").strip()}
        for source, (target, limit) in FIELDS.items():
            value = fields.get(source, "")
            if len(value) > limit:
                errors.append("Row %d: %s exceeds %d characters" % (index, source, limit))
                break
            record[target] = value
        else:
            studies[key] = record
    if errors:
        raise ValueError("Import validation failed: " + "; ".join(errors[:10]))
    return studies

def table():
    connection = __import__("os").environ["RESEARCHPASS_STORAGE_CONNECTION"]
    service = TableServiceClient.from_connection_string(connection)
    service.create_table_if_not_exists("ResearchPassStudies")
    return service.get_table_client("ResearchPassStudies")

def plan(raw):
    incoming = parse_xml(raw)
    client = table()
    changes = []
    counts = {"create": 0, "update": 0, "unchanged": 0}
    for key, data in incoming.items():
        try:
            existing = client.get_entity(partition_key="STUDY", row_key=key)
        except ResourceNotFoundError:
            existing = None
        if existing is None:
            action = "create"
        else:
            protected = set(json.loads(existing.get("xml_override_fields", "[]")))
            # Existing owner-managed settings are never overwritten merely by importing XML.
            if existing.get("contact_override"):
                protected.update(("pi_name", "contact_email", "contact_phone", "study_contact"))
            changed = any(
                field not in protected and (field not in existing or existing.get(field) != value)
                for field, value in data.items() if field != "irb_number"
            )
            action = "update" if changed else "unchanged"
        counts[action] += 1
        changes.append({"irb_number": data["irb_number"], "study_title": data["study_title"], "action": action})
    return {"counts": counts, "total": len(incoming), "studies": changes, "sha256": hashlib.sha256(raw).hexdigest()}

def apply(raw, expected_sha, actor):
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("The selected file changed since preview; preview it again")
    incoming = parse_xml(raw)
    client = table()
    now = datetime.now(timezone.utc).isoformat()
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for key, data in incoming.items():
        try:
            entity = client.get_entity(partition_key="STUDY", row_key=key)
            new = False
        except ResourceNotFoundError:
            entity = {"PartitionKey": "STUDY", "RowKey": key, "study_status": "inactive",
                      "created_by": "institutional_xml_import", "created_at": now}
            new = True
        protected = set(json.loads(entity.get("xml_override_fields", "[]")))
        if entity.get("contact_override"):
            protected.update(("pi_name", "contact_email", "contact_phone", "study_contact"))
        changed = new
        for field, value in data.items():
            if field == "irb_number" and not new:
                continue
            if field in protected and not new:
                continue
            if entity.get(field) != value:
                entity[field] = value
                changed = True
        entity["xml_last_imported_at"] = now
        entity["xml_imported_by"] = actor
        entity["xml_source_sha256"] = expected_sha
        if new:
            client.create_entity(entity)
            counts["created"] += 1
        else:
            client.update_entity(entity, mode="merge")
            counts["updated" if changed else "unchanged"] += 1
    return {"counts": counts, "total": len(incoming), "imported_at": now, "access_granted": False}
