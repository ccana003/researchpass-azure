"""Study memberships keyed by normalized IRB and Entra object ID."""
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
