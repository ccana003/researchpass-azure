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
        return entity.get("role")
    except ResourceNotFoundError:
        return None

def grant_owner(irb_number, user_id):
    # This is called only after successfully creating the study.
    try:
        table().create_entity({"PartitionKey": normalize_irb(irb_number), "RowKey": user_id, "role": "owner"})
    except ResourceExistsError:
        pass

def grant_issuer(irb_number, user_id):
    # Never overwrite an existing owner or issuer membership.
    try:
        table().create_entity({"PartitionKey": normalize_irb(irb_number), "RowKey": user_id, "role": "issuer"})
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
