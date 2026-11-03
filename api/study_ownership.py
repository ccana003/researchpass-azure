"""Study owner assignment helpers."""
from memberships import table
from azure.data.tables import UpdateMode
from studies import normalize_irb

def assign(irb, user_id):
    key = normalize_irb(irb)
    table().upsert_entity({'PartitionKey': key, 'RowKey': user_id, 'role': 'owner', 'active': True}, mode=UpdateMode.MERGE)
    return {'irb_number': irb, 'role': 'owner'}
