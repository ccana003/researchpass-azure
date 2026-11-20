"""Study-wide, non-personal participant information. No participant records."""
import base64
import json
import os
import re
from azure.data.tables import TableServiceClient, UpdateMode
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceNotFoundError
from studies import normalize_irb

CONTAINER="researchpass-public-study-resources"
KINDS={"consent":"Unsigned consent reference","medication":"General medication information","guide":"Participant guide","faq":"Study FAQ","directions":"Locations and directions"}
MAX_PDF=5*1024*1024

def study(irb):
    key=normalize_irb(irb)
    connection=os.environ["RESEARCHPASS_STORAGE_CONNECTION"]
    client=TableServiceClient.from_connection_string(connection).get_table_client("ResearchPassStudies")
    try: return client,client.get_entity(partition_key="STUDY",row_key=key)
    except ResourceNotFoundError: raise ValueError("Study not found") from None

def get(irb,public=False):
    _,s=study(irb)
    if public and (not s.get("hub_published",False) or s.get("study_status") not in ("active","registered")):
        raise ValueError("This study information page is not published")
    docs=json.loads(s.get("hub_documents","[]"))
    return {"irb_number":s.get("irb_number",normalize_irb(irb)),"study_title":s.get("study_title",""),"published":bool(s.get("hub_published",False)),"overview":s.get("hub_overview",""),"contacts":s.get("hub_contacts",""),"resources":docs}

def save(irb,payload):
    if not isinstance(payload,dict): raise ValueError("JSON object required")
    fields={}
    for key in ("overview","contacts"):
        value=payload.get(key,"")
        if not isinstance(value,str) or len(value)>3000: raise ValueError(key+" must be 3,000 characters or fewer")
        fields["hub_"+key]=value.strip()
    if not isinstance(payload.get("published"),bool): raise ValueError("published must be true or false")
    fields["hub_published"]=payload["published"]
    client,_=study(irb)
    client.update_entity({"PartitionKey":"STUDY","RowKey":normalize_irb(irb),**fields},mode=UpdateMode.MERGE)
    return get(irb)

def upload(irb,payload):
    if not isinstance(payload,dict): raise ValueError("JSON object required")
    kind=payload.get("kind")
    if kind not in KINDS: raise ValueError("Unsupported document category")
    filename=payload.get("filename","")
    if not isinstance(filename,str) or not re.fullmatch(r"[a-zA-Z0-9 _().-]{1,120}\\.pdf",filename,re.I):
        raise ValueError("Only PDF files with safe filenames are allowed")
    try: raw=base64.b64decode(payload.get("content_base64",""),validate=True)
    except Exception: raise ValueError("Invalid PDF data") from None
    if not raw.startswith(b"%PDF-") or len(raw)>MAX_PDF or len(raw)<8:
        raise ValueError("Upload must be a PDF of 5 MB or less")
    client,s=study(irb)
    docs=json.loads(s.get("hub_documents","[]"))
    if len(docs)>=20: raise ValueError("Maximum of 20 documents per study")
    from uuid import uuid4
    doc_id=uuid4().hex
    blob=BlobServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    blob.create_container(CONTAINER) if not blob.get_container_client(CONTAINER).exists() else None
    blob.get_blob_client(CONTAINER,normalize_irb(irb)+"/"+doc_id+".pdf").upload_blob(raw,overwrite=False,content_settings=ContentSettings(content_type="application/pdf"))
    docs.append({"id":doc_id,"kind":kind,"filename":filename})
    client.update_entity({"PartitionKey":"STUDY","RowKey":normalize_irb(irb),"hub_documents":json.dumps(docs)},mode=UpdateMode.MERGE)
    return get(irb)

def remove(irb,doc_id):
    if not re.fullmatch(r"[a-f0-9]{32}",doc_id): raise ValueError("Invalid document ID")
    client,s=study(irb)
    docs=json.loads(s.get("hub_documents","[]"))
    if not any(d["id"]==doc_id for d in docs): raise ValueError("Document not found")
    remaining=[d for d in docs if d["id"]!=doc_id]
    # Unpublish before removing to avoid dangling public links.
    client.update_entity({"PartitionKey":"STUDY","RowKey":normalize_irb(irb),"hub_published":False,"hub_documents":json.dumps(remaining)},mode=UpdateMode.MERGE)
    BlobServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"]).get_blob_client(CONTAINER,normalize_irb(irb)+"/"+doc_id+".pdf").delete_blob()
    return get(irb)

def download(irb,doc_id):
    data=get(irb,public=True)
    if not any(d["id"]==doc_id for d in data["resources"]): raise ValueError("Document not published")
    blob=BlobServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"]).get_blob_client(CONTAINER,normalize_irb(irb)+"/"+doc_id+".pdf")
    return blob.download_blob().readall()
