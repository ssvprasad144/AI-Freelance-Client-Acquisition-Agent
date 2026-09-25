# AI Freelance Client Acquisition Agent

Local-first AI-assisted lead discovery, qualification, proposal drafting, follow-up, and outreach management for SSVPrasad.

## V1
- Mock-first development
- Human approval before outreach
- Optional GPT-4o-mini
- No fabricated experience or outcomes
- Permitted APIs/public sources only

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
