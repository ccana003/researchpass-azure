# ResearchPass POC authentication (temporary local accounts)

Entra ID is not available yet. The API now supports invitation-gated local accounts with PBKDF2-HMAC-SHA256 salted password hashes and signed, 8-hour bearer sessions. **Use synthetic studies and participant data only.** The POC is not approved for production or PHI.

## One-time Azure settings required

In `researchpass-api-dev` > Settings > Environment variables > App settings, add:

- `RESEARCHPASS_SESSION_SECRET`: a randomly generated secret of at least 32 characters (ideally 48+ cryptographically random bytes encoded as hex). Do not commit it to GitHub or share in chat.
- `RESEARCHPASS_INVITE_CODE`: a separate unpredictable invitation code of at least 20 characters. Share privately only with authorized POC testers.
- `RESEARCHPASS_STORAGE_CONNECTION`: existing connection string (already configured).

The `ResearchPassUsers` and `ResearchPassStudyUsers` Azure Tables are created automatically on first use. No Entra settings are needed for the temporary mode.

## API endpoints

- `POST /api/account/register` (anonymous function route, but requires private invitation code): `{"email":"tester@example.org","password":"long unique passphrase","invite_code":"..."}`
- `POST /api/account/login` (anonymous function route): `{"email":"tester@example.org","password":"..."}` -> bearer token
- `POST /api/studies` (Azure Function key + bearer token): `{"irb_number":"POC-2026-002","study_title":"Synthetic POC"}`
- `GET /api/studies/{irb_number}/access` (Function key + bearer token)
- `POST /api/studies/{irb_number}/users` (owner only, Function key + bearer token): `{"user_object_id":"<local user_id UUID returned on registration>"}`

A user who registers a new study is assigned its owner role; owners may grant issuer access to other registered POC accounts.

## Limitations and next steps

- The registration and login routes are internet-reachable. There is no rate limiting, email verification, password reset, or account lockout. Keep the invitation code secret, restrict network access if possible, and do not invite real users yet.
- Do not put the Azure Function key or bearer tokens in public browser JavaScript. The frontend is intentionally not connected to these endpoints yet. Use Azure Test/Run or trusted server-side tools for controlled tests.
- An interrupted write between study creation and owner membership can leave an orphaned study; administrative recovery is needed.
- Email addresses are account identifiers but are not verified.
- The old Entra-specific `auth.py` remains available for later migration but is not active.
- Replace local authentication with institutional identity, audit logging, secure session management, invitation acceptance, and security review before any real-world deployment.
