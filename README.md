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

## Automated discovery worker

The discovery worker runs live public-web discovery, deduplicates results, and automatically qualifies previously unanalyzed new leads using the configured GPT-4o-mini qualification model. It does not send outbound messages.

Run one cycle:

    cd backend
    python manage.py run_discovery_cycle

Run continuously:

    cd backend
    python manage.py run_discovery_cycle --loop

The loop interval defaults to `DISCOVERY_WORKER_INTERVAL=3600` seconds and is configurable through the environment. Each cycle records a `discovery.completed` activity event with discovered, created, duplicate, analyzed, and qualified counts. The dashboard exposes the latest discovery timestamp and result summary.

Windows launcher: `start-discovery-worker.bat`.

Human approval remains required for proposals and follow-ups, and external outreach is not sent by the worker.

## Production deployment

The backend supports PostgreSQL through `DATABASE_URL`, production HTTPS settings, and a Gunicorn WSGI process. `render.yaml` defines the API web service and the separate discovery worker. Configure secrets and environment-specific values in the hosting platform before deploying; do not commit real credentials.

Required production variables include `DJANGO_SECRET_KEY`, `DATABASE_URL`, `OPENAI_API_KEY`, `ALLOWED_HOSTS`, and `CORS_ALLOWED_ORIGINS`. The discovery and follow-up workers remain separate from the API process. External outreach is not enabled by these services.
