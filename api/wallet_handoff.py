"""Short-lived, one-time, opaque QR handoff for synthetic ResearchPass passes."""
import base64
import hashlib
import io
import json
import os
import secrets
import time
import uuid
from datetime import date, datetime, timezone

import qrcode
from cryptography.fernet import Fernet
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError, ResourceModifiedError

TABLE = "ResearchPassWalletHandoffs"
LIFETIME = 15 * 60

def _table():
    client = TableServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    client.create_table_if_not_exists(TABLE)
    return client.get_table_client(TABLE)

def _cipher():
    secret = os.environ["RESEARCHPASS_SESSION_SECRET"].encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"researchpass-handoff-v1:"+secret).digest()))

def _url(token):
    base = os.environ.get("RESEARCHPASS_PUBLIC_API_BASE", "https://researchpass-api-dev-czc2e6b8d8fyg0c6.eastus2-01.azurewebsites.net").rstrip("/")
    return base + "/api/wallet-handoff/" + token

def _qr(url):
    image = qrcode.make(url, box_size=5, border=3)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()

def create(irb, issuer_id, settings, system_settings, payload):
    from apple_wallet import build_pass
    from google_wallet import generate_save_url
    name = payload.get("participant_name")
    start = payload.get("start_date") or ""
    end = payload.get("end_date") or ""
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Synthetic participant name is required (1-100 characters)")
    for key, val, required in (("start_date", start, settings.get("require_start_date")),("end_date", end, settings.get("require_end_date"))):
        if not isinstance(val, str) or (required and not val):
            raise ValueError(key + " is required or invalid")
        if val:
            date.fromisoformat(val)
    if start and end and end < start:
        raise ValueError("End date cannot precede start date")
    # Validate both providers before issuing QR codes.
    apple_data, apple_serial = build_pass(settings, system_settings, name, start, end)
    wallet_settings = {**system_settings, **settings, "platform_label": system_settings.get("platform_label", "Miami CTSI")}
    google_url, google_object = generate_save_url(wallet_settings, name, start, end, return_details=True)
    issuance = uuid.uuid4().hex
    expiry = int(time.time()) + LIFETIME
    table = _table()
    result = {"issuance_id": issuance, "expires_at": datetime.fromtimestamp(expiry, timezone.utc).isoformat(), "wallets": {}}
    # The encrypted pass and URL exist only temporarily; neither appears in QR links.
    for platform, data, object_id in (("apple", apple_data, apple_serial), ("google", google_url.encode(), google_object)):
        token = secrets.token_urlsafe(32)
        ciphertext = _cipher().encrypt(data).decode()
        table.create_entity({
            "PartitionKey": issuance, "RowKey": platform, "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "payload": ciphertext, "expires_at": expiry, "status": "generated",
            "irb": irb, "issuer_id": issuer_id, "object_id": object_id,
            "study_title": settings.get("display_name", ""),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        url = _url(issuance + "." + platform + "." + token)
        result["wallets"][platform] = {"url": url, "qr_png": _qr(url), "status": "generated"}
    return result

def open_handoff(raw_token):
    from pass_registry import record
    try:
        issuance, platform, token = raw_token.split(".")
    except ValueError:
        return None
    if len(issuance)!=32 or platform not in ("apple","google") or len(token)<30:
        return None
    table = _table()
    try:
        entity = table.get_entity(partition_key=issuance, row_key=platform)
    except ResourceNotFoundError:
        return None
    if not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), entity.get("token_hash", "")):
        return None
    if int(entity.get("expires_at", 0)) < int(time.time()) or entity.get("status") != "generated":
        return None
    data = _cipher().decrypt(entity["payload"].encode())
    # Optimistic concurrency: only one redemption may succeed.
    entity["status"] = "opened"
    entity["opened_at"] = datetime.now(timezone.utc).isoformat()
    entity["payload"] = ""
    try:
        table.update_entity(entity, mode="replace", etag=entity.metadata["etag"], match_condition="IfNotModified")
    except ResourceModifiedError:
        return None
    record(entity["irb"], entity["object_id"], entity["issuer_id"], entity.get("study_title", ""),
           platform="Apple Wallet" if platform=="apple" else "Google Wallet", status="opened")
    return platform, data
