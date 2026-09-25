# AI Freelance Client Acquisition Agent

Production-oriented AI-assisted freelance opportunity discovery, qualification, proposal drafting, follow-up and outreach management.

## Live discovery
The primary discovery path uses the OpenAI Responses API with its hosted `web_search` tool to find current publicly available opportunities. Results are normalized into the existing Lead model and deduplicated before storage.

## Outreach safety
No login bypass or unauthorized scraping. Outbound communication remains a human-approved draft workflow.

## API
POST `/api/discovery/run/`
```json
{"query":"AI automation Django React freelance","source":"live"}
```
Use `source":"mock"` for regression tests.

## Production flow
Live Web Search → Lead Extraction → Deduplication → PostgreSQL → AI Qualification → Proposal Draft → Human Approval → Outreach/Follow-up.

Keep `OPENAI_API_KEY` server-side.
