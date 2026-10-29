"""Study memberships keyed by normalized IRB and ResearchPass user ID."""
import os
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from studies import normalize_irb

TABLE_NAME = "ResearchPassStudyUsers"

def table():
    connection = os.environ.get("RESEARCHPASS_STORAGE_CONNECTION")
    if not connection:
        raise RuntimeError("Study storage is not configured")
    service = TableServiceClient.from_connection_string(connection)
    service.create_table_if_not_exists(TABLE_NAME)
    return service.get_table_client(TABLE_NAME)

def role_for(irb_number, user_id):
    try:
        entity = table().get_entity(partition_key=normalize_irb(irb_number), row_key=user_id)
        return entity.get("role") if entity.get("active", True) else None
    except ResourceNotFoundError:
        return None

def grant_owner(irb_number, user_id):
    # This is called only after successfully creating the study.
    try:
        table().create_entity({"PartitionKey": normalize_irb(irb_number), "RowKey": user_id, "role": "owner", "active": True})
    except ResourceExistsError:
        pass

def grant_issuer(irb_number, user_id):
    # Never overwrite an existing owner or issuer membership.
    try:
        table().create_entity({"PartitionKey": normalize_irb(irb_number), "RowKey": user_id, "role": "issuer", "active": True})
    except ResourceExistsError:
        pass


def studies_for_user(user_id):
    """Return memberships belonging to the signed-in user (POC table scan)."""
    from azure.data.tables import TableServiceClient
    connection = os.environ.get("RESEARCHPASS_STORAGE_CONNECTION")
    if not connection:
        raise RuntimeError("Study storage is not configured")
    service = TableServiceClient.from_connection_string(connection)
    memberships = table().query_entities(
        query_filter="RowKey eq @uid", parameters={"uid": user_id}
    )
    studies_client = service.get_table_client("ResearchPassStudies")
    result = []
    for membership in memberships:
        if not membership.get("active", True):
            continue
        irb = membership["PartitionKey"]
        try:
            study = studies_client.get_entity(partition_key="STUDY", row_key=irb)
        except ResourceNotFoundError:
            continue
        result.append({
            "irb_number": study.get("irb_number", irb),
            "study_title": study.get("study_title", ""),
            "study_status": study.get("study_status", "registered"),
            "role": membership.get("role", "issuer"),
        })
    return sorted(result, key=lambda item: item["study_title"].casefold())

def list_all_study_access():
    """Admin-only caller: return memberships with study metadata and user emails."""
    from local_auth import users_table
    service = TableServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    studies = {s["RowKey"]: s for s in service.get_table_client("ResearchPassStudies").list_entities()}
    emails = {u.get("user_id"): u["RowKey"] for u in users_table().list_entities()}
    results = []
    for member in table().list_entities():
        study = studies.get(member["PartitionKey"], {})
        results.append({
            "study_id": member["PartitionKey"],
            "study_title": study.get("study_title", ""),
            "user_id": member["RowKey"],
            "email": emails.get(member["RowKey"], member.get("demo_email", "Unknown account")),
            "demo": bool(member.get("demo_tag")),
            "role": member.get("role", "issuer"),
            "active": bool(member.get("active", True)),
        })
    return sorted(results, key=lambda x: (x["study_id"], x["role"] != "owner", x["email"]))

def set_membership_active(irb_number, user_id, active):
    from azure.data.tables import UpdateMode
    from azure.core.exceptions import ResourceNotFoundError
    key = normalize_irb(irb_number)
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("Valid user ID required")
    client = table()
    entity = client.get_entity(partition_key=key, row_key=user_id)
    if entity.get("role") == "owner":
        raise ValueError("Study owner access cannot be changed here")
    client.update_entity({"PartitionKey": key, "RowKey": user_id, "active": bool(active)}, mode=UpdateMode.MERGE)
    return {"study_id": key, "user_id": user_id, "active": bool(active)}
