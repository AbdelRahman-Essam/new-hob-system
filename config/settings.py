import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core / environment -----------------------------------------------------
# All of these are read from the environment so the same code runs safely in
# dev (defaults below) and in production (real values set in /etc/newhope.env
# or a systemd EnvironmentFile — see DEPLOY.md).
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
DEBUG = os.environ.get("DEBUG", "1") == "1"

# Comma-separated, e.g. "yourname.duckdns.org,www.yourname.duckdns.org"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# Needed by Django's CSRF check when the site sits behind Nginx over HTTPS.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "feed",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves static files fast, with far-future cache headers
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "feed.context.branding",
    ]}}]
WSGI_APPLICATION = "config.wsgi.application"

# --- Database ----------------------------------------------------------------
# Kept as SQLite by request (simple, fine for a small number of concurrent users).
# `timeout` makes writers wait instead of immediately raising "database is locked"
# under brief concurrent access, and WAL mode (enabled in feed/apps.py) lets reads
# and writes happen at the same time instead of blocking each other.
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / "db.sqlite3",
    "OPTIONS": {"timeout": 20},
}}

# --- Caching -------------------------------------------------------------
# Local in-memory cache (per-process). Used to avoid re-querying the single
# AppSettings row on every transaction status check (see feed/models.py).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "newhope-cache"}}

LANGUAGE_CODE = "en-us"   # Arabic text is in the templates; keeps digits/dates predictable
TIME_ZONE = "Africa/Cairo"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Security (only meaningful once DEBUG=0, i.e. real deployment) ----------
if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # trust Nginx's proxy header
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    X_FRAME_OPTIONS = "DENY"

# Contact details shown in the app (edit here)
APP_NAME_AR = "إدارة سحوبات علف نيوهوب"
APP_NAME_EN = "New Hope Feed Manager"
CONTACT_NAME = "م / أحمد غنيم"
CONTACT_PHONE = "01556665054"

# Send unhandled 500 tracebacks to console/journal even with DEBUG=0
# (Django's default only mails them to ADMINS, which isn't configured here).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
