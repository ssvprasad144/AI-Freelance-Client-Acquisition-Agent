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


## Follow-up worker

Approved follow-ups are automatically moved to the `due` state when their scheduled time arrives. The worker never sends external messages.

Run one processing cycle:

```bash
cd backend
python manage.py process_due_followups
```

Run continuously:

```bash
cd backend
python manage.py process_due_followups --loop
```

The loop interval defaults to `FOLLOWUP_WORKER_INTERVAL=60` seconds and can be changed through the environment. The processor is idempotent, so repeated cycles do not duplicate the due transition or activity log.

The intended lifecycle is:

`Draft → Approved → Due → Ready for Action`

External outreach remains a separate, human-controlled step. The worker does not send email, platform messages, or other outbound communication.
