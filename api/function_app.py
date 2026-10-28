import json
import logging
import re
import azure.functions as func
from studies import create_study, DuplicateStudyError, normalize_irb
from local_auth import authenticate, register, login, LocalAuthError, LocalAuthNotConfigured
from memberships import grant_owner, grant_issuer, role_for, studies_for_user

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def response(payload, status):
    return func.HttpResponse(json.dumps(payload), status_code=status, mimetype="application/json")

def current_user(req):
    try:
        return authenticate(req), None
    except LocalAuthNotConfigured:
        return None, response({"error": "POC authentication settings are not configured"}, 503)
    except LocalAuthError as exc:
        return None, response({"error": str(exc)}, 401)

@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return response({"status": "ok", "application": "ResearchPass", "environment": "development", "service": "api"}, 200)

@app.route(route="account/register", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def register_account(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        if not isinstance(payload, dict):
            return response({"error": "JSON object required"}, 400)
        result = register(payload.get("email"), payload.get("password"), payload.get("invite_code"))
        return response(result, 201)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except LocalAuthError as exc:
        return response({"error": str(exc)}, 403)
    except LocalAuthNotConfigured:
        return response({"error": "POC authentication settings are not configured"}, 503)
    except Exception:
        logging.exception("POC account registration failed")
        return response({"error": "Unable to register account"}, 500)

@app.route(route="account/login", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def login_account(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        if not isinstance(payload, dict):
            return response({"error": "JSON object required"}, 400)
        return response(login(payload.get("email"), payload.get("password")), 200)
    except ValueError:
        return response({"error": "Invalid email or password"}, 401)
    except LocalAuthError as exc:
        return response({"error": str(exc)}, 401)
    except LocalAuthNotConfigured:
        return response({"error": "POC authentication settings are not configured"}, 503)
    except Exception:
        logging.exception("POC login failed")
        return response({"error": "Unable to sign in"}, 500)

@app.route(route="studies", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def register_study(req: func.HttpRequest) -> func.HttpResponse:
    # POC-only: signed user session required; no browser-exposed Function key.
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

@app.route(route="studies/{irb_number}/access", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
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

@app.route(route="studies/{irb_number}/users", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
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
            return response({"error": "A valid ResearchPass user ID is required"}, 400)
        grant_issuer(irb_number, target.lower())
        return response({"irb_number": normalize_irb(irb_number), "user_object_id": target.lower(), "role": "issuer"}, 201)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except Exception:
        logging.exception("Study user grant failed")
        return response({"error": "Unable to grant access"}, 500)


@app.route(route="my-studies", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def my_studies(req: func.HttpRequest) -> func.HttpResponse:
    user_id, error = current_user(req)
    if error is not None:
        return error
    try:
        return response({"studies": studies_for_user(user_id)}, 200)
    except Exception:
        logging.exception("Unable to list user studies")
        return response({"error": "Unable to load your studies"}, 500)


@app.route(route="studies/{irb_number}/settings", methods=["GET", "PUT"], auth_level=func.AuthLevel.ANONYMOUS)
def study_settings(req: func.HttpRequest) -> func.HttpResponse:
    from study_settings import get_settings, save_settings
    user_id, error = current_user(req)
    if error is not None:
        return error
    irb = req.route_params["irb_number"]
    try:
        role = role_for(irb, user_id)
        if not role:
            return response({"error": "Access denied"}, 403)
        if req.method == "PUT":
            if role != "owner":
                return response({"error": "Only study owners can edit settings"}, 403)
            return response(save_settings(irb, req.get_json()), 200)
        return response(get_settings(irb), 200)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except Exception:
        logging.exception("Study settings operation failed")
        return response({"error": "Unable to load or save study settings"}, 500)


@app.route(route="studies/{irb_number}/pass-preview", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def pass_preview(req: func.HttpRequest) -> func.HttpResponse:
    """Synthetic-only preview; does not issue, sign, or store a wallet pass."""
    from datetime import date
    from study_settings import get_settings
    user_id, error = current_user(req)
    if error is not None:
        return error
    try:
        irb = req.route_params["irb_number"]
        if role_for(irb, user_id) not in ("owner", "issuer"):
            return response({"error": "Access denied"}, 403)
        payload = req.get_json()
        if not isinstance(payload, dict):
            return response({"error": "JSON object required"}, 400)
        name = payload.get("participant_name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            return response({"error": "Synthetic participant name is required (1-100 characters)"}, 400)
        settings = get_settings(irb)
        dates = {}
        for field, required in (("start_date", "require_start_date"), ("end_date", "require_end_date")):
            value = payload.get(field) or ""
            if not isinstance(value, str):
                return response({"error": field + " must be a date"}, 400)
            if settings[required] and not value:
                return response({"error": field + " is required by this study"}, 400)
            if value:
                try:
                    dates[field] = date.fromisoformat(value)
                except ValueError:
                    return response({"error": field + " must use YYYY-MM-DD"}, 400)
        if dates.get("start_date") and dates.get("end_date") and dates["end_date"] < dates["start_date"]:
            return response({"error": "End date cannot precede start date"}, 400)
        return response({
            "preview_only": True,
            "message": "Synthetic preview only; no wallet pass was generated or saved",
            "participant_name": name.strip(),
            "irb_number": settings["irb_number"],
            "study_name": settings["display_name"],
            "pi_name": settings["pi_name"],
            "contact_email": settings["contact_email"],
            "contact_phone": settings["contact_phone"],
            "start_date": dates["start_date"].isoformat() if "start_date" in dates else None,
            "end_date": dates["end_date"].isoformat() if "end_date" in dates else None,
        }, 200)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except Exception:
        logging.exception("Pass preview failed")
        return response({"error": "Unable to prepare preview"}, 500)


@app.route(route="admin/me", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def admin_me(req: func.HttpRequest) -> func.HttpResponse:
    from system_admin import is_admin
    user_id, error = current_user(req)
    if error is not None:
        return error
    return response({"system_admin": is_admin(user_id)}, 200)

@app.route(route="admin/wallet-settings", methods=["GET", "PUT"], auth_level=func.AuthLevel.ANONYMOUS)
def admin_wallet_settings(req: func.HttpRequest) -> func.HttpResponse:
    from system_admin import is_admin, read_settings, write_settings
    user_id, error = current_user(req)
    if error is not None:
        return error
    if not is_admin(user_id):
        return response({"error": "System administrator access required"}, 403)
    try:
        if req.method == "PUT":
            return response(write_settings(req.get_json()), 200)
        return response(read_settings(), 200)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except Exception:
        logging.exception("System administration settings failed")
        return response({"error": "Unable to manage system settings"}, 500)
