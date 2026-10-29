"""Admin-controlled, tagged synthetic demonstration records for the ResearchPass POC.

No real participants, wallet objects, or usable user credentials are created.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError
from studies import normalize_irb

TAG = "researchpass_demo_v1"
STUDIES = [
    ("DEMO26001", "Synthetic Breast Cancer Research Study"),
    ("DEMO26002", "Synthetic Lung Cancer Screening Study"),
    ("DEMO26003", "Synthetic Leukemia Outcomes Study"),
    ("DEMO26004", "Synthetic Myeloma Treatment Study"),
    ("DEMO26005", "Synthetic Colorectal Cancer Study"),
    ("DEMO26006", "Synthetic Prostate Cancer Study"),
    ("DEMO26007", "Synthetic Immunotherapy Study"),
    ("DEMO26008", "Synthetic Pediatric Oncology Study"),
    ("DEMO26009", "Synthetic Survivorship Study"),
    ("DEMO26010", "Synthetic Precision Oncology Study"),
]

def clients():
    service = TableServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    return {
        name: service.create_table_if_not_exists(name)
        for name in ("ResearchPassStudies", "ResearchPassStudyUsers", "ResearchPassPassEvents")
    }

def demo_user(study_idx, slot):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"researchpass/demo/v1/{study_idx}/{slot}"))

def load_demo():
    tables = clients()
    now = datetime.now(timezone.utc)
    for idx, (irb, title) in enumerate(STUDIES):
        tables["ResearchPassStudies"].upsert_entity({
            "PartitionKey": "STUDY", "RowKey": irb,
            "irb_number": irb, "study_title": title, "study_status": "registered",
            "created_by": demo_user(idx, 0), "created_at": (now - timedelta(days=100-idx)).isoformat(),
            "demo_tag": TAG,
        })
        for slot in range(3):
            user_id = demo_user(idx, slot)
            tables["ResearchPassStudyUsers"].upsert_entity({
                "PartitionKey": irb, "RowKey": user_id,
                "role": "owner" if slot == 0 else "issuer",
                "active": not (slot == 2 and idx % 2 == 0),
                "demo_email": f"demo.study{idx+1:02d}.{'owner' if slot==0 else 'issuer'+str(slot)}@example.org",
                "demo_tag": TAG,
            })
        for j in range(6):
            object_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"researchpass/demo/v1/pass/{idx}/{j}")).replace("-", "")
            tables["ResearchPassPassEvents"].upsert_entity({
                "PartitionKey": irb, "RowKey": object_id,
                "wallet_object_id": "DEMO." + object_id,
                "issuer_id": demo_user(idx, j % 2),
                "study_title": title,
                "platform": "Google Wallet",
                "status": "simulated_link_generated",
                "created_at": (now - timedelta(days=idx * 6 + j, hours=j * 2)).isoformat(),
                "demo_tag": TAG,
            })
    return {"studies": len(STUDIES), "memberships": len(STUDIES)*3, "simulated_passes": len(STUDIES)*6}

def clear_demo():
    tables = clients()
    counts = {"studies": 0, "memberships": 0, "simulated_passes": 0}
    for table_name, key in (("ResearchPassPassEvents", "simulated_passes"), ("ResearchPassStudyUsers", "memberships"), ("ResearchPassStudies", "studies")):
        table = tables[table_name]
        for entity in table.list_entities():
            if entity.get("demo_tag") != TAG:
                continue
            table.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])
            counts[key] += 1
    return counts
