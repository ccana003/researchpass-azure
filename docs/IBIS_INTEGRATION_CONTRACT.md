# ResearchPass ↔ IBIS: IT integration contract (v0.1)

## Scope
ResearchPass exposes a receiving endpoint for IT to connect to the institution's IBIS/IRB system. **No IBIS URL, API authentication, or field mappings have been assumed or implemented.** IT owns the upstream IBIS connector and maps its response to the canonical payload below.

### Endpoint
`POST https://researchpass-api-dev-czc2e6b8d8fyg0c6.eastus2-01.azurewebsites.net/api/integrations/ibis/studies`

- Header `Content-Type: application/json`
- Header `x-researchpass-integration-key: <secret>`
- Configure `RESEARCHPASS_IBIS_INTEGRATION_KEY` in **researchpass-api-dev** Azure Function App environment variables with a random 32+ character secret; share it with IT through approved secret management, not email or GitHub.
- HTTPS only. For production, replace shared key with managed identity / OAuth and gateway restrictions as approved by IT.
- API returns 401 when not configured or when secret is invalid.
- **Existing studies only**: register the study in ResearchPass first. Sync returns 404 if not found. Sync never creates accounts, grants study access, or authorizes issuers.
- The entire payload is a canonical ResearchPass contract; IT determines actual IBIS field mapping.

### Request JSON example (synthetic data)
```json
{
  "protocol_number": "POC-2026-003",
  "study_title": "Synthetic Study Example",
  "principal_investigator": "Dr. Example Investigator",
  "contact_email": "research@example.edu",
  "contact_phone": "305-555-0100",
  "study_team": [
    {"name": "Example Coordinator", "email": "coordinator@example.edu", "role": "Coordinator"},
    {"name": "Example Investigator", "email": "pi@example.edu", "role": "Principal Investigator"}
  ]
}
```

### Response JSON example
```json
{"protocol_number":"POC-2026-003","status":"synced","study_team_count":2,"access_granted":false,"synced_at":"2026-10-29T15:00:00+00:00"}
```

### Data mapping and governance
- `protocol_number` → study lookup key (case-insensitive, punctuation-normalized)
- `study_title` → canonical study title; `principal_investigator` → `pi_name`
- `contact_email` and `contact_phone` → study contact details
- `study_team` → separate IBIS roster, **not** ResearchPass user permissions
- Sync timestamp is recorded. Existing display-name overrides are retained.
- This version does not implement scheduled polling, webhook verification, incremental synchronization, automated account provisioning, or changes to study authorization.
- Study team names and emails may be personal data: restrict connector access, confirm retention rules, and use approved institutional privacy/security controls before sending real records.
- The endpoint currently uses the existing POC infrastructure and must be security-reviewed before production use.

### IT prerequisites
1. Confirm IBIS API availability, access approval, and actual field mappings.
2. Configure the secret on both sides through approved secret management.
3. Test with a pre-registered synthetic ResearchPass study.
4. Define refresh cadence, source-of-truth rules, error handling, and deprovisioning.
5. Obtain institutional security/privacy review before transmitting real study team data.

### Mandatory pass attribution
Apple and Google wallet builders both hard-code the non-editable `Author` field:
> This pass was developed by the University of Miami CTSI with support from grant UM1TR004556 of the National Center for Advancing Translational Sciences.
