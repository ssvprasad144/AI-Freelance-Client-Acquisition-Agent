from pathlib import Path
import os
from dotenv import load_dotenv
BASE_DIR=Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent/".env")
SECRET_KEY=os.getenv("DJANGO_SECRET_KEY","dev-only-secret-key")
DEBUG=os.getenv("DEBUG","True").lower()=="true"
ALLOWED_HOSTS=[x.strip() for x in os.getenv("ALLOWED_HOSTS","127.0.0.1,localhost").split(",") if x.strip()]
INSTALLED_APPS=["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","corsheaders","rest_framework","leads"]
MIDDLEWARE=["corsheaders.middleware.CorsMiddleware","django.middleware.security.SecurityMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","django.contrib.messages.middleware.MessageMiddleware","django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF="config.urls"; TEMPLATES=[{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]; WSGI_APPLICATION="config.wsgi.application"
if os.getenv("DATABASE_URL"):
    import dj_database_url
    DATABASES={"default":dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=600, ssl_require=True)}
else:
    DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}
LANGUAGE_CODE="en-us"; TIME_ZONE="Asia/Kolkata"; USE_I18N=True; USE_TZ=True; STATIC_URL="static/"; DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
CORS_ALLOWED_ORIGINS=[x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS","http://localhost:5173").split(",") if x.strip()]
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY",""); OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-4o-mini")
DISCOVERY_MODEL=os.getenv("DISCOVERY_MODEL","gpt-4o-mini"); DISCOVERY_MAX_RESULTS=int(os.getenv("DISCOVERY_MAX_RESULTS","20")); DISCOVERY_SEARCH_CONTEXT_SIZE=os.getenv("DISCOVERY_SEARCH_CONTEXT_SIZE","medium")
DEFAULT_DISCOVERY_QUERY=os.getenv("DEFAULT_DISCOVERY_QUERY","Find current freelance opportunities matching AI products, business automation, Django/React full-stack development, and Three.js interactive web development")
QUALIFICATION_MIN_SCORE=int(os.getenv("QUALIFICATION_MIN_SCORE","60"))
FOLLOWUP_WORKER_INTERVAL=int(os.getenv("FOLLOWUP_WORKER_INTERVAL","60"))
DISCOVERY_WORKER_INTERVAL=int(os.getenv("DISCOVERY_WORKER_INTERVAL","3600"))
MOCK_LEADS_FILE=BASE_DIR/"leads"/"data"/"mock_freelance_leads_100.json"
FREELANCE_SEARCH_PROFILE={"name":"SSVPrasad","services":["AI Products","Business Automation","Full-Stack Development","Interactive Web"],"skills":["Python","C++","JavaScript","SQL","React","Vite","Three.js","React Three Fiber","Django","Django REST Framework","PostgreSQL","SQLite","OpenAI","webhooks","GitHub","Render","GitHub Pages","Cloudinary","Linux"],"projects":[{"name":"AI Business Automation Dashboard","evidence":"AI workflow demos, execution logging, dashboard and backend APIs."},{"name":"CareerInnTech","evidence":"Django-based career platform with AI interview functionality and PostgreSQL."},{"name":"AI Interview","evidence":"Voice-first AI mock interview experience with Django and frontend integration."},{"name":"3D Motion Portfolio","evidence":"React/Three.js portfolio focused on interactive web experiences."}]}
REST_FRAMEWORK={"DEFAULT_RENDERER_CLASSES":["rest_framework.renderers.JSONRenderer","rest_framework.renderers.BrowsableAPIRenderer"]}
if not DEBUG:
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")
    SECURE_SSL_REDIRECT=os.getenv("SECURE_SSL_REDIRECT","true").lower()=="true"
    SESSION_COOKIE_SECURE=True
    CSRF_COOKIE_SECURE=True
    X_FRAME_OPTIONS="DENY"
