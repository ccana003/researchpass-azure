"""Generate signed Apple Wallet .pkpass for synthetic ResearchPass POC records.

Uses existing Azure environment PEM certificate material and institutional branding.
No participant details are persisted.
"""
import base64
import hashlib
import io
import json
import os
import re
import uuid
import zipfile
from datetime import date

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from PIL import Image

def _pem_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError("Apple Wallet signing is not configured: " + name)
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise RuntimeError("Invalid Apple Wallet signing configuration: " + name) from exc

def _rgb(hex_color):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color or ""):
        hex_color = "#005030"
    return "rgb(" + ",".join(str(int(hex_color[i:i+2], 16)) for i in (1,3,5)) + ")"

def _assets():
    from branding_assets import get_asset
    raw = get_asset("logo")
    if not raw:
        raise RuntimeError("Upload the institutional logo in System administration before generating Apple Wallet passes.")
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    # Reuse the institutionally managed logo. Apple requires separate icon sizes.
    result = {}
    for name, size in (("icon.png", (29,29)), ("icon@2x.png", (58,58)), ("logo.png", (160,50)), ("logo@2x.png", (320,100))):
        if name.startswith("icon"):
            side = min(image.size)
            icon = image.crop(((image.width-side)//2,(image.height-side)//2,(image.width+side)//2,(image.height+side)//2))
            resized = icon.resize(size, Image.Resampling.LANCZOS)
        else:
            resized = Image.new("RGBA", size, (0,0,0,0))
            logo = image.copy()
            logo.thumbnail(size, Image.Resampling.LANCZOS)
            resized.alpha_composite(logo, ((size[0]-logo.width)//2,(size[1]-logo.height)//2))
        output = io.BytesIO()
        resized.save(output, format="PNG")
        result[name] = output.getvalue()
    return result

def build_pass(settings, system_settings, name, start_date="", end_date=""):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Synthetic participant name is required (1-100 characters)")
    for field, value, required in (
        ("start_date", start_date, settings.get("require_start_date", False)),
        ("end_date", end_date, settings.get("require_end_date", False)),
    ):
        if not isinstance(value, str):
            raise ValueError(field + " must use YYYY-MM-DD")
        if required and not value:
            raise ValueError(field + " is required by this study")
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(field + " must use YYYY-MM-DD") from exc
    if start_date and end_date and end_date < start_date:
        raise ValueError("End date cannot precede start date")
    pass_type = os.environ.get("APPLE_PASS_TYPE_IDENTIFIER", "").strip()
    team = os.environ.get("APPLE_TEAM_IDENTIFIER", "").strip()
    if not pass_type or not team:
        raise RuntimeError("Apple Wallet Pass Type ID and Team ID are not configured")
    cert = x509.load_pem_x509_certificate(_pem_env("APPLE_SIGNER_CERT_BASE64"))
    key = serialization.load_pem_private_key(_pem_env("APPLE_SIGNERKEY_BASE64"), password=None)
    wwdr = x509.load_pem_x509_certificate(_pem_env("APPLE_WWDR_BASE64"))
    serial = uuid.uuid4().hex
    study_title = str(settings.get("display_name") or "ResearchPass Study")[:100]
    irb = str(settings.get("irb_number") or "")[:64]
    def field(key, label, value):
        return {"key": key, "label": label, "value": str(value or "—")}
    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": pass_type,
        "teamIdentifier": team,
        "serialNumber": serial,
        "organizationName": "University of Miami",
        "description": "Research Participant ID (Synthetic POC)",
        "backgroundColor": _rgb(system_settings.get("card_background", "#005030")),
        "foregroundColor": "rgb(255,255,255)",
        "labelColor": "rgb(255,255,255)",
        "barcodes": [{"format":"PKBarcodeFormatQR","message":serial,"messageEncoding":"iso-8859-1"}],
        "generic": {
            "headerFields": [field("org", "Organization", "University of Miami")],
            "primaryFields": [field("participant", "Participant", name.strip())],
            "secondaryFields": [field("study", "Study", study_title), field("pi", "Principal Investigator", settings.get("pi_name"))],
            "auxiliaryFields": [field("start", "Start Date", start_date), field("end", "End Date", end_date), field("contact", "Contact", settings.get("contact_email"))],
            "backFields": [field("irb", "Study protocol", irb), field("author", "Author", "This pass was developed by the University of Miami CTSI with support from grant UM1TR004556 of the National Center for Advancing Translational Sciences.")],
        },
    }
    files = {"pass.json": json.dumps(pass_json, ensure_ascii=False, separators=(",",":")).encode("utf-8")}
    files.update(_assets())
    manifest = {filename: hashlib.sha1(data).hexdigest() for filename, data in files.items()}
    manifest_bytes = json.dumps(manifest, separators=(",",":")).encode("utf-8")
    builder = pkcs7.PKCS7SignatureBuilder().set_data(manifest_bytes).add_signer(cert, key, hashes.SHA256()).add_certificate(wwdr)
    signature = builder.sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary])
    files["manifest.json"] = manifest_bytes
    files["signature"] = signature
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, data in files.items():
            archive.writestr(filename, data)
    return output.getvalue(), serial
