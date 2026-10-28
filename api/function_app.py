
import json
import azure.functions as func

app = func.FunctionApp(
    http_auth_level=func.AuthLevel.ANONYMOUS
)

@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "application": "ResearchPass",
            "environment": "development",
            "service": "api"
        }),
        mimetype="application/json",
        status_code=200
    )
