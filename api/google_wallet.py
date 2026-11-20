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
    # A class-level homepage must be unique to each study.
    irb_for_class = re.sub(r"[^A-Za-z0-9._-]", "_", str(settings.get("irb_number") or ""))[:48]
    class_id = f"{issuer_id}.{class_suffix}_{irb_for_class}" if irb_for_class else f"{issuer_id}.{class_suffix}"
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
        "header": {"defaultValue": {"language": "en-US", "value": participant_name.strip()}},
        "subheader": {"defaultValue": {"language": "en-US", "value": study_name}},
        "textModulesData": [
            {"id": "participant_name", "header": "Participant", "body": participant_name.strip()},
            {"id": "study_name", "header": "Study", "body": study_name},
            {"id": "principal_investigator", "header": "Principal Investigator", "body": str(settings.get("pi_name") or "Not provided")[:250]},
            {"header": "Study protocol", "body": irb_number},
            {"header": "Study contact email", "body": str(settings.get("contact_email") or "Not provided")[:250]},
            {"header": "Study contact phone", "body": str(settings.get("contact_phone") or "Not provided")[:250]},
            {"id": "institutional_author", "header": "Author", "body": "This pass was developed by the University of Miami CTSI with support from grant UM1TR004556 of the National Center for Advancing Translational Sciences."},
        ],
    }
    hub_url = settings.get("participant_hub_url")
    if hub_url:
        # Google Pass Builder places homepageUri on the GenericClass.
        # A study-specific class ID prevents the URL leaking across studies.
        generic_class["homepageUri"] = {
            "uri": hub_url,
            "description": "Study Information & Resources",
        }
        generic_object["linksModuleData"] = {
            "uris": [{
                "id": "link-0",
                "uri": hub_url,
                "description": "Study Information & Resources"
            }]
        }
        generic_object["textModulesData"].insert(1, {
            "id": "participant_resources",
            "header": "Study Information & Resources",
            "body": "Open the study's general information, documents, and contacts using the link below."
        })
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
        generic_object["textModulesData"].insert(3, {"header": "Study start", "body": start_date})
    if end_date:
        generic_object["textModulesData"].insert(4 if start_date else 3, {"header": "Study end", "body": end_date})

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

def inspect_saved_object(object_id, class_id):
    """Read back only link metadata from Google's stored Wallet resources."""
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode, quote
    from urllib.request import Request, urlopen

    account = _service_account()
    now = int(time.time())
    assertion = jwt.encode({
        "iss": account["client_email"],
        "scope": "https://www.googleapis.com/auth/wallet_object.issuer",
        "aud": account.get("token_uri", "https://oauth2.googleapis.com/token"),
        "iat": now,
        "exp": now + 3600,
    }, account["private_key"], algorithm="RS256")
    token_req = Request(
        account.get("token_uri", "https://oauth2.googleapis.com/token"),
        data=urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(token_req, timeout=12) as r:
            access_token = json.load(r)["access_token"]
    except (HTTPError, URLError, KeyError) as exc:
        raise RuntimeError("Unable to authenticate to Google Wallet API") from exc

    def fetch(kind, resource_id):
        url = "https://walletobjects.googleapis.com/walletobjects/v1/" + kind + "/" + quote(resource_id, safe="")
        request = Request(url, headers={"Authorization": "Bearer " + access_token})
        try:
            with urlopen(request, timeout=12) as r:
                return json.load(r), 200
        except HTTPError as exc:
            if exc.code == 404:
                return None, 404
            raise RuntimeError("Google Wallet API rejected " + kind + " lookup (HTTP " + str(exc.code) + ")") from exc
        except URLError as exc:
            raise RuntimeError("Unable to reach Google Wallet API") from exc

    obj, object_status = fetch("genericObject", object_id)
    cls, class_status = fetch("genericClass", class_id)
    links = ((obj or {}).get("linksModuleData") or {}).get("uris") or []
    homepage = (cls or {}).get("homepageUri") or {}
    return {
        "object_found": object_status == 200,
        "class_found": class_status == 200,
        "object_has_resources_link": any(link.get("id") == "link-0" for link in links),
        "object_link_count": len(links),
        "class_has_homepage": bool(homepage.get("uri")),
        "object_state": (obj or {}).get("state"),
    }
