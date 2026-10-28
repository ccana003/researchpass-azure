# Authentication and study authorization (POC)

Backend identity checks are implemented but **not yet activated**. No real-user study registration or participant ID issuance is enabled.

## Configuration required from Azure/University IT
1. Register or identify a Microsoft Entra ID application for the ResearchPass API in the University of Miami tenant.
2. Expose a delegated API scope for signed-in users and grant appropriate consent.
3. Set Azure Function App settings:
   - `RESEARCHPASS_ENTRA_TENANT_ID`: the University's Entra tenant GUID.
   - `RESEARCHPASS_ENTRA_API_AUDIENCE`: the exact `aud` value of access tokens issued for the ResearchPass API (usually its application client ID).
4. The backend verifies RS256 signatures using Microsoft's JWKS, plus issuer, audience, tenant, expiry, and delegated-user claim.
5. Current Azure Function key protection is retained as an additional gate. Never expose a Function key in browser JavaScript.

## Authorization model
- Successful registration creates a study and an owner membership, keyed by normalized IRB number and Entra user object ID.
- An owner can grant issuer access by Entra user object ID.
- An issuer can check their study access, but cannot grant other users access.
- Study user records are stored in the `ResearchPassStudyUsers` Azure Table, created on first membership operation.
- No external IRB staff verification or Velos integration is performed in the POC.
- The issuance API and login UI are **not implemented**. Study-specific authorization must be checked again by every future issuance operation.

## Security limitations before production
- Study registration and owner membership use separate Azure Table writes; an interrupted operation can leave a study without an owner. Add recovery/administrative reconciliation before production.
- Invitation by Entra object ID is an internal POC mechanism; implement identity lookup, user acceptance, and audit logging before real-world rollout.
- A function key plus Entra token is required for current backend routes. A server-side proxy or managed API integration is required before browser-based use.
- Until Entra settings are configured, study endpoints fail closed with HTTP 503.
