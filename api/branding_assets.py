"""Central administrator-controlled branding assets in private Azure Blob Storage."""
import base64
import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from system_admin import settings_table

CONTAINER = "researchpass-branding"
MAX_BYTES = 800_000

def blob_client(name):
    if name not in ("hero", "logo"):
        raise ValueError("Unsupported branding asset")
    service = BlobServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    return service.get_blob_client(CONTAINER, name + ".png")

def save_asset(name, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), str):
        raise ValueError("PNG image data is required")
    try:
        content = base64.b64decode(payload["data"], validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 image") from exc
    if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > MAX_BYTES:
        raise ValueError("Upload a PNG image smaller than 800 KB")
    service = BlobServiceClient.from_connection_string(os.environ["RESEARCHPASS_STORAGE_CONNECTION"])
    service.create_container(CONTAINER) if not service.get_container_client(CONTAINER).exists() else None
    service.get_blob_client(CONTAINER, name + ".png").upload_blob(content, overwrite=True, content_settings=__import__("azure.storage.blob", fromlist=["ContentSettings"]).ContentSettings(content_type="image/png"))
    settings_table().upsert_entity({"PartitionKey": "SYSTEM", "RowKey": "WALLET", "asset_" + name: True}, mode="merge")

def get_asset(name):
    try:
        return blob_client(name).download_blob().readall()
    except ResourceNotFoundError:
        return None
