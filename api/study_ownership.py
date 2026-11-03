"""Study owner assignment helpers."""
from memberships import table
from azure.data.tables import UpdateMode
from studies import normalize_irb

def assign(irb, user_id):
    key = normalize_irb(irb)
    table().upsert_entity({'PartitionKey': key, 'RowKey': user_id, 'role': 'owner', 'active': True}, mode=UpdateMode.MERGE)
    return {'irb_number': irb, 'role': 'owner'}

from azure.core.exceptions import ResourceNotFoundError
from local_auth import users_table, normalized_email
from study_xml_import import table as studies_table

def account(email):
    try:
        return users_table().get_entity(partition_key="USER",row_key=normalized_email(email))
    except ResourceNotFoundError:
        raise ValueError("ResearchPass account not found")

def assign_by_email(irb,email):
    user=account(email)
    if not user.get("active"):
        raise ValueError("Account is inactive")
    key=normalize_irb(irb)
    try:
        studies_table().get_entity(partition_key="STUDY",row_key=key)
    except ResourceNotFoundError:
        raise ValueError("Study not found")
    return assign(key,user["user_id"])

def eligible_studies(user_id):
    from memberships import role_for
    user=next((u for u in users_table().list_entities() if u.get("user_id")==user_id and u.get("active")),None)
    if user is None:
        raise ValueError("Account not found")
    if not user.get("email_verified",False):
        return {"email_verified":False,"studies":[]}
    email=user["RowKey"].strip().lower()
    matches=[]
    for s in studies_table().query_entities("PartitionKey eq 'STUDY'"):
        if s.get("study_status") not in ("active","registered"):
            continue
        eligible=[s.get("pi_email",""),s.get("institutional_contact_email",s.get("contact_email",""))]
        if email not in [str(v).strip().lower() for v in eligible if v]:
            continue
        if role_for(s.get("irb_number",s["RowKey"]),user_id)=="owner":
            continue
        matches.append({"irb_number":s.get("irb_number",s["RowKey"]),"study_title":s.get("study_title","")})
    return {"email_verified":True,"studies":matches}

def claim(irb,user_id):
    key=normalize_irb(irb)
    matches=eligible_studies(user_id)
    if not matches["email_verified"]:
        raise PermissionError("Your email must be verified before claiming a study")
    if key not in [normalize_irb(s["irb_number"]) for s in matches["studies"]]:
        raise PermissionError("This study is not eligible for your account")
    return assign(irb,user_id)

def verify_account(email):
    user=account(email)
    users_table().update_entity({"PartitionKey":"USER","RowKey":normalized_email(email),"email_verified":True},mode=UpdateMode.MERGE)
    return {"email":normalized_email(email),"email_verified":True}

def set_pi_email(irb,email):
    key=normalize_irb(irb)
    try:
        studies_table().get_entity(partition_key="STUDY",row_key=key)
    except ResourceNotFoundError:
        raise ValueError("Study not found")
    studies_table().update_entity({"PartitionKey":"STUDY","RowKey":key,"pi_email":normalized_email(email)},mode=UpdateMode.MERGE)
    return {"irb_number":irb,"pi_email":normalized_email(email)}
