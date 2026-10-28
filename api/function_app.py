import json
import logging
import re
import azure.functions as func
from studies import create_study, DuplicateStudyError, normalize_irb
from auth import authenticate, AuthenticationError, AuthenticationNotConfigured
from memberships import grant_owner, grant_issuer, role_for

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

def response(payload, status):
    return func.HttpResponse(json.dumps(payload), status_code=status, mimetype="application/json")

def current_user(req):
    try:
        return authenticate(req), None
    except AuthenticationNotConfigured:
        return None, response({"error": "Microsoft Entra authentication must be configured before using study endpoints"}, 503)
    except AuthenticationError as exc:
        return None, response({"error": str(exc)}, 401)

@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return response({"status": "ok", "application": "ResearchPass", "environment": "development", "service": "api"}, 200)

@app.route(route="studies", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def register_study(req: func.HttpRequest) -> func.HttpResponse:
    # Both an Azure Function key and a validated Entra delegated user token are required.
    user_id, error = current_user(req)
    if error is not None:
        return error
    try:
        payload = req.get_json()
    except ValueError:
        return response({"error": "Request body must be valid JSON"}, 400)
    if not isinstance(payload, dict):
        return response({"error": "Request body must be a JSON object"}, 400)
    try:
        result = create_study(payload.get("irb_number"), payload.get("study_title"), user_id)
        grant_owner(result["irb_number"], user_id)
        return response(result, 201)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except DuplicateStudyError as exc:
        return response({"error": str(exc)}, 409)
    except Exception:
        logging.exception("Study registration or owner assignment failed")
        return response({"error": "Unable to complete study registration; administrator review may be required"}, 500)

@app.route(route="studies/{irb_number}/access", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def study_access(req: func.HttpRequest) -> func.HttpResponse:
    user_id, error = current_user(req)
    if error is not None:
        return error
    try:
        role = role_for(req.route_params["irb_number"], user_id)
        if not role:
            return response({"error": "Access denied"}, 403)
        return response({"irb_number": normalize_irb(req.route_params["irb_number"]), "role": role}, 200)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except Exception:
        logging.exception("Study access lookup failed")
        return response({"error": "Unable to check access"}, 500)

@app.route(route="studies/{irb_number}/users", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def add_study_user(req: func.HttpRequest) -> func.HttpResponse:
    user_id, error = current_user(req)
    if error is not None:
        return error
    try:
        irb_number = req.route_params["irb_number"]
        if role_for(irb_number, user_id) != "owner":
            return response({"error": "Only study owners can grant access"}, 403)
        payload = req.get_json()
        target = payload.get("user_object_id") if isinstance(payload, dict) else None
        if not isinstance(target, str) or not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,40}", target):
            return response({"error": "A valid Entra user object ID is required"}, 400)
        grant_issuer(irb_number, target.lower())
        return response({"irb_number": normalize_irb(irb_number), "user_object_id": target.lower(), "role": "issuer"}, 201)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except Exception:
        logging.exception("Study user grant failed")
        return response({"error": "Unable to grant access"}, 500)
