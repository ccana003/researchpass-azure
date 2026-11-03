"""Administrator-only institutional study inventory and activation."""
from datetime import datetime, timezone
from azure.core.exceptions import ResourceNotFoundError
from study_xml_import import table
from studies import normalize_irb

PUBLIC_FIELDS = ("irb_number","study_title","pi_name","study_contact","contact_email","contact_phone","institutional_status","velos_study_status","study_status","xml_last_imported_at","created_at","created_by","display_name","study_notes","xml_imported_by")
def clean(entity):
    result={k:entity.get(k,"") for k in PUBLIC_FIELDS}
    result["irb_number"]=result["irb_number"] or entity.get("RowKey","")
    # Include other imported metadata, but never storage identifiers, secrets, or internal override flags.
    for k,v in entity.items():
        if k.startswith(("xml_","institutional_","velos_")) and k not in ("xml_override_fields","xml_source_sha256") and isinstance(v,(str,int,float,bool)):
            result[k]=v
    return result

def all_studies():
    client=table()
    rows=[clean(e) for e in client.query_entities("PartitionKey eq 'STUDY'")]
    rows.sort(key=lambda s:(s["study_title"] or "").lower())
    return {"studies":rows,"total":len(rows)}

def set_status(irb,status):
    if status not in ("active","inactive"):
        raise ValueError("Status must be active or inactive")
    key=normalize_irb(irb)
    client=table()
    try:
        entity=client.get_entity(partition_key="STUDY",row_key=key)
    except ResourceNotFoundError as exc:
        raise ValueError("Study not found") from exc
    entity["study_status"]=status
    entity["status_updated_at"]=datetime.now(timezone.utc).isoformat()
    client.update_entity(entity,mode="merge")
    return {"study":clean(entity),"message":"Study status updated; membership permissions are unchanged"}

def is_issuance_enabled(irb):
    key=normalize_irb(irb)
    try:
        entity=table().get_entity(partition_key="STUDY",row_key=key)
    except ResourceNotFoundError:
        return False
    return entity.get("study_status") in ("active","registered")
