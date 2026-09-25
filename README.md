# AI Freelance Client Acquisition Agent

A local-first AI-assisted lead discovery, qualification, proposal drafting, follow-up, and outreach management system for SSVPrasad.

## V1 principles

- Mock-first development: no external lead scraping or outbound messages.
- Human approval before any outreach.
- GPT-4o-mini is optional; deterministic fallbacks keep development free.
- Never invent experience, clients, revenue, integrations, or outcomes.
- Use permitted APIs/public sources only when real discovery adapters are introduced.

## Architecture

React/Vite → Django REST API → SQLite (V1) → optional OpenAI API

## Local setup

Backend:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

Backend: http://127.0.0.1:8000  
Frontend: http://localhost:5173
