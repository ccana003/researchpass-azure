"""Validate Microsoft Entra ID access tokens for the ResearchPass API."""
import os
import jwt
from jwt import PyJWKClient

class AuthenticationError(Exception):
    pass

class AuthenticationNotConfigured(Exception):
    pass

def authenticate(req):
    tenant = os.environ.get("RESEARCHPASS_ENTRA_TENANT_ID", "").strip()
    audience = os.environ.get("RESEARCHPASS_ENTRA_API_AUDIENCE", "").strip()
    if not tenant or not audience:
        raise AuthenticationNotConfigured("Microsoft Entra authentication is not configured")
    authorization = req.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise AuthenticationError("A Microsoft Entra access token is required")
    token = authorization[7:].strip()
    if not token:
        raise AuthenticationError("An access token is required")
    try:
        # Validate the signature, expiry, audience, tenant, and issuer.
        jwks = PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys")
        key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=audience,
            issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss", "tid", "oid"]},
            leeway=60,
        )
        if claims["tid"].lower() != tenant.lower():
            raise AuthenticationError("Incorrect tenant")
        # Delegated user token only; reject app-only credentials.
        if not claims.get("scp"):
            raise AuthenticationError("A delegated user access token is required")
        return claims["oid"]
    except AuthenticationError:
        raise
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired access token") from exc
