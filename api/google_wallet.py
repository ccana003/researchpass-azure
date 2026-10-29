"""Google Wallet save-link generation for synthetic ResearchPass POC passes."""
import json
import os
import re
import time
import uuid

import jwt


def _service_account():
    raw = os.getenv("RESEARCHPASS_GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("Google Wallet service account key is not configured in Azure.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Google Wallet service account configuration is not valid JSON.") from exc
    if data.get("type") != "service_account" or not data.get("client_email") or not data.get("private_key"):
        raise RuntimeError("Google Wallet configuration must be a service account JSON key.")
    return data


def generate_save_url(settings, participant_name, start_date="", end_date="", return_details=False):
    """Return a signed Google Wallet save URL. Never stores participant data."""
    issuer_id = str(settings.get("google_issuer_id", "")).strip()
    class_suffix = str(settings.get("google_class_id", "")).strip()
    if not issuer_id or not class_suffix:
        raise RuntimeError("Set the Google Wallet Issuer ID and class ID suffix in System administration first.")
    if not re.fullmatch(r"[0-9]+", issuer_id):
        raise RuntimeError("Google Wallet Issuer ID must contain digits only.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", class_suffix):
        raise RuntimeError("Google Wallet class ID suffix contains unsupported characters.")
    if not isinstance(participant_name, str) or not 1 <= len(participant_name.strip()) <= 100:
        raise ValueError("Synthetic participant name is required (1-100 characters).")

    account = _service_account()
    class_id = f"{issuer_id}.{class_suffix}"
    object_suffix = uuid.uuid4().hex
    object_id = f"{issuer_id}.{object_suffix}"
    study_name = str(settings.get("display_name") or "ResearchPass Study")[:100]
    irb_number = str(settings.get("irb_number") or "")[:64]

    generic_class = {
        "id": class_id,
        "issuerName": str(settings.get("platform_label") or "Miami CTSI")[:50],
        "reviewStatus": "UNDER_REVIEW",
    }
    generic_object = {
        "id": object_id,
        "classId": class_id,
        "state": "ACTIVE",
        "cardTitle": {"defaultValue": {"language": "en-US", "value": "ResearchPass"}},
        "header": {"defaultValue": {"language": "en-US", "value": study_name}},
        "subheader": {"defaultValue": {"language": "en-US", "value": participant_name.strip()}},
        "barcode": {"type": "QR_CODE", "value": object_id},
        "textModulesData": [
            {"header": "Study protocol", "body": irb_number},
            {"header": "Study contact email", "body": str(settings.get("contact_email") or "Not provided")[:250]},
            {"header": "Study contact phone", "body": str(settings.get("contact_phone") or "Not provided")[:250]},
            {"id": "institutional_author", "header": "Author", "body": "This pass was developed by the University of Miami CTSI with support from grant UM1TR004556 of the National Center for Advancing Translational Sciences."},
        ],
    }
    if settings.get("study_notes"):
        generic_object["textModulesData"].append({"id": "study_notes", "header": "Study description / notes", "body": str(settings["study_notes"])[:1000]})
    color = str(settings.get("card_background") or "#005030")
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        generic_object["hexBackgroundColor"] = color
    base_url = os.getenv("RESEARCHPASS_PUBLIC_API_BASE", "https://researchpass-api-dev-czc2e6b8d8fyg0c6.eastus2-01.azurewebsites.net").rstrip("/")
    assets = settings.get("branding_assets") or {}
    if assets.get("logo"):
        generic_object["logo"] = {"sourceUri": {"uri": base_url + "/api/wallet-branding/logo"}}
    if assets.get("hero"):
        generic_object["heroImage"] = {"sourceUri": {"uri": base_url + "/api/wallet-branding/hero"}}
    if start_date:
        generic_object["textModulesData"].append({"header": "Study start", "body": start_date})
    if end_date:
        generic_object["textModulesData"].append({"header": "Study end", "body": end_date})

    origins = [item.strip() for item in os.getenv("RESEARCHPASS_WALLET_ORIGINS", "").split(",") if item.strip()]
    claims = {
        "iss": account["client_email"],
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "origins": origins,
        "payload": {
            "genericClasses": [generic_class],
            "genericObjects": [generic_object],
        },
    }
    token = jwt.encode(claims, account["private_key"], algorithm="RS256")
    url = "https://pay.google.com/gp/v/save/" + token
    if len(url) > 8000:
        raise ValueError("The generated Google Wallet link is too long. Shorten the study or participant display text and try again.")
    return (url, object_id) if return_details else url
