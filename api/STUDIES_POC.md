# Study registration POC

POST /api/studies accepts JSON with required `irb_number` and `study_title`.

- The IRB number is normalized to uppercase alphanumeric characters and used as the Azure Table Storage RowKey under PartitionKey STUDY.
- Azure Table Storage create_entity is atomic: duplicate keys produce HTTP 409.
- Table name: ResearchPassStudies.
- Required Function App setting: RESEARCHPASS_STORAGE_CONNECTION.
- HTTP function-key authentication is temporary and intended for controlled POC testing only. Do not put a function key in browser-side code or publish the registration interface before Microsoft Entra ID authentication and per-study authorization are implemented.
- Do not use real participant information for POC tests.
- Study status is entered locally; Velos status sync and study personnel verification are future integrations.

Sample test payload:
```json
{"irb_number":"POC-2026-001","study_title":"Synthetic ResearchPass POC Study"}
```

Expected: first request 201, repeated normalized IRB 409, invalid IRB 400, missing function key 401/403.
