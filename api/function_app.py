import json
import logging
import azure.functions as func
from studies import create_study, DuplicateStudyError

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

def response(payload, status):
    return func.HttpResponse(json.dumps(payload), status_code=status, mimetype="application/json")

@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return response({"status": "ok", "application": "ResearchPass", "environment": "development", "service": "api"}, 200)

@app.route(route="studies", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def register_study(req: func.HttpRequest) -> func.HttpResponse:
    # Function keys are a temporary POC gate, not end-user authentication.
    # Do not expose this endpoint in the public portal until Entra login and
    # study-specific authorization have been implemented.
    try:
        payload = req.get_json()
    except ValueError:
        return response({"error": "Request body must be valid JSON"}, 400)
    if not isinstance(payload, dict):
        return response({"error": "Request body must be a JSON object"}, 400)
    try:
        result = create_study(
            payload.get("irb_number"),
            payload.get("study_title"),
            "poc-function-key"
        )
        return response(result, 201)
    except ValueError as exc:
        return response({"error": str(exc)}, 400)
    except DuplicateStudyError as exc:
        return response({"error": str(exc)}, 409)
    except Exception:
        logging.exception("Study registration failed")
        return response({"error": "Unable to register study"}, 500)
