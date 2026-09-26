# AI Freelance Client Acquisition Agent

Production-oriented AI-assisted freelance opportunity discovery, qualification, proposal drafting, follow-up and outreach management.

## Security and access

The API uses Django REST Framework token authentication. The health endpoint is public for hosting health checks; application data and write endpoints require authentication.

Create the first account with:

    cd backend
    python manage.py createsuperuser

Then sign in through the frontend. Never commit passwords, API keys, database URLs or Django secrets.

API protection includes:
- authenticated application endpoints
- explicit AI and discovery rate limits
- global anonymous/user throttling
- paginated list endpoints
- production HTTPS/security headers
- server-side OpenAI credentials only

## Live discovery

The primary discovery path uses the OpenAI Responses API with its hosted web_search tool to find current publicly available opportunities. Results are normalized into the Lead model and deduplicated before storage.

No login bypass or unauthorized scraping is used.

## Pipeline

Live Web Search -> Lead Extraction -> Deduplication -> PostgreSQL -> AI Qualification -> Proposal Draft -> Human Approval -> Follow-up / Reply Tracking.

Lead lifecycle statuses:

new -> qualified -> proposal -> contacted -> replied -> won/lost

Status changes are explicit user actions. Reply tracking is manual and does not send outbound communication.

## Outreach safety

Proposal approval and follow-up approval do not send external messages. The follow-up worker only moves approved follow-ups to due.

## API

- GET /api/health/
- POST /api/auth/login/
- GET /api/auth/me/
- GET /api/dashboard/
- GET /api/leads/
- POST /api/discovery/run/
- POST /api/discovery/qualify/
- GET /api/leads/qualified/
- POST /api/leads/<id>/set_status/
- POST /api/leads/<id>/replies/
- GET /api/replies/
- GET /api/followups/
- POST /api/followups/create/
- POST /api/followups/<id>/approve/
- GET /api/followups/due/
- POST /api/followups/process-due/

List endpoints are paginated with a default page size of 50 and a maximum of 100.

## Workers and monitoring

The discovery and follow-up workers write heartbeat and error events. GET /api/health/ exposes worker status so hosting and operators can detect stale workers.

Discovery defaults to one cycle per hour. Follow-up processing defaults to every 60 seconds.

Neither worker sends external communication.

## Frontend

The React/Vite frontend includes:
- authenticated sign-in
- live discovery
- qualification and proposal workflow
- lead lifecycle controls
- reply tracking
- follow-up scheduling and approval
- due-action queue
- worker health visibility
- responsive production UI

## Production deployment

The backend supports PostgreSQL through DATABASE_URL, production HTTPS settings, and Gunicorn. render.yaml defines the API, discovery worker, follow-up worker and frontend static site.

Required hosting values include DJANGO_SECRET_KEY, DATABASE_URL, OPENAI_API_KEY, ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, and frontend VITE_API_BASE_URL.

Configure these in the hosting platform; do not commit real credentials.

## Development checks

Backend:

    cd backend
    pip install -r requirements.txt
    python manage.py test

Frontend:

    cd frontend
    npm install
    npm run build

GitHub Actions runs both backend tests and the frontend production build on pushes and pull requests to main.
