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


## Client acquisition engine

The acquisition layer now includes:
- four discovery profiles covering AI/automation, Django/full-stack, interactive web and startup MVP opportunities
- automated multi-profile discovery worker
- evidence-based proposal personalization using the actual profile/project knowledge
- reply intent/sentiment classification with a deterministic fallback when AI is unavailable
- acquisition funnel analytics at `/api/analytics/`
- source and lead-type conversion breakdowns
- guarded email outreach at `/api/outreach/<id>/send/`
- explicit `OUTREACH_ENABLED=false` safety default
- manual approval before any outreach can be sent
- no automatic platform messaging or unauthorized scraping


### Safe public-web crawler

Live search results can now be enriched by a conservative public-web crawler. The crawler:
- fetches only HTTP(S) public pages
- checks `robots.txt` before crawling
- blocks loopback, private, link-local, reserved, multicast and unspecified IP destinations
- blocks URLs containing embedded credentials
- follows only a small number of validated redirects
- enforces per-domain request delays and page budgets
- limits response size, text size, links and timeout
- accepts HTML/XHTML/JSON only
- does not log in, submit forms, execute JavaScript, solve CAPTCHAs, bypass access controls, or use proxies
- enriches only URLs already discovered by the live search layer
- remains disabled if `CRAWLER_ENABLED=false`

The crawler uses Python's standard library, so no additional scraping framework is required.


### Discovery cost optimization

Automated discovery uses a rotating set of four focused profiles. The worker runs one profile per cycle and uses measured search performance to balance exploration of under-tested profiles with exploitation of higher-yield profiles.

The discovery pipeline is:

Search/inventory gate -> query freshness cache -> one rotating profile -> live web search -> URL/title/company dedupe -> deterministic pre-filter -> targeted public-page enrichment -> qualification -> qualified lead.

Default production settings:
- discovery interval: 6 hours
- query cache TTL: 72 hours
- one adaptive profile per cycle with a 2-search exploration floor
- maximum 4 live searches per day
- stop searching when 10 fresh qualified leads are available
- search context: low
- deterministic pre-filter threshold: 40
- crawl only top 5 candidates per cycle
- maximum 8 AI qualification candidates per cycle
- proposals allowed only for qualified leads
- outbound communication remains approval/provider gated

The worker now measures qualified leads per search, created leads per search, replies per search, and wins per search. Profiles with fewer than the configured exploration minimum are tested first; after that, higher measured yield receives priority. The default learning window is 30 days. This keeps search spend bounded while progressively concentrating the budget on better-performing discovery strategies without permanently starving newer strategies.

### Web-search cost intelligence v2

The discovery engine now applies ten cost controls before and around paid web search:
1. search-necessity gating from fresh qualified inventory and recent cache state
2. semantic query deduplication and cross-profile result reuse
3. source-domain performance tracking with temporary suppression of consistently low-yield domains
4. adaptive search-context sizing based on arm performance
5. query-variant evolution across base, recent, client-request and project formulations
6. freshness-aware inventory and cache reuse
7. qualification/reply/win feedback at search, arm and domain levels
8. configurable preferred discovery hours to avoid low-value timing
9. cross-profile reuse of compatible recent search results
10. dynamic daily search budgeting: the four-search ceiling is a ceiling, not a target

These controls are local Django/PostgreSQL logic. They do not add an AI training job or an extra model call merely to choose a search. A paid web search is made only after the local gates allow it. The existing 72-hour query cache, 30-day learning window, 4-search daily ceiling, local prefilter and crawler/qualification limits remain in place.


### Source-aware proposal and outreach center

Each discovered lead stores both its original `source_url` and an actionable `action_url` when discovery can verify a distinct public destination. Proposal generation maps the lead to a delivery medium and action: marketplace bid, LinkedIn DM, Reddit reply, GitHub response, email, job application, or contact form.

The Outreach Center presents each ready proposal with the exact destination, a copy-proposal action, and the correct completion workflow. Manual channels are tracked as opened/submitted without pretending the platform submission happened automatically. Email remains separately gated by `OUTREACH_ENABLED` and SMTP configuration.

Outreach endpoints include:
- GET /api/outreach/ready/
- POST /api/outreach/<id>/open/
- POST /api/outreach/<id>/mark-submitted/
- POST /api/outreach/<id>/send/ (email only, approved + provider gated)


## Phase 16-18 Production Hardening
Autonomous acquisition actions, safe multichannel outreach, revenue attribution, continuous learning, and deployment-safe migrations are enabled with approval-required automation by default.
