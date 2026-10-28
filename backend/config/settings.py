"""
Django settings for the Rhombus regex-replacement backend.

All environment-specific values are read from environment variables (12-factor style),
so the same code runs locally, in CI and on EC2. A local `.env` file is loaded for
convenience during development.
"""

import os
import re
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")
    SECRET_KEY = "dev-only-insecure-secret-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "datasets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves Django's static files and the built React app (see WHITENOISE_ROOT).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite locally; PostgreSQL in production via DATABASE_URL.
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# The built React app (`npm run build`) is served from the site root, so the frontend
# and the API share one origin in production just like with the Vite proxy in development.
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST
    WHITENOISE_INDEX_FILE = True


def _is_immutable_file(path: str, url: str) -> bool:
    """Content-hashed files never change, so browsers may cache them forever.

    Matches Vite output (`/assets/index-DtaNHwhb.js`) and Django's manifest storage
    (`app.3f2a1b9c0d4e.css`). index.html is not matched and is always revalidated.
    """
    return bool(re.search(r"^/assets/.+-[\w-]{8}\.\w+$|\.[0-9a-f]{12}\.\w+$", url))


WHITENOISE_IMMUTABLE_FILE_TEST = _is_immutable_file

# Uploaded originals and processed Parquet files.
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "EXCEPTION_HANDLER": "datasets.exception_handler.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
    # Per-IP limits on the expensive endpoints (LLM calls cost money, uploads use disk).
    "DEFAULT_THROTTLE_RATES": {
        "preview": os.getenv("THROTTLE_PREVIEW", "60/hour"),
        "upload": os.getenv("THROTTLE_UPLOAD", "30/hour"),
    },
    # Number of reverse proxies in front of Django (Caddy = 1). Used to read the real
    # client IP from X-Forwarded-For without trusting client-supplied values.
    "NUM_PROXIES": int(os.getenv("NUM_PROXIES", "0")),
}

# Throttle counters live in the cache. In production use the database so every gunicorn
# worker shares the same counts; in-process memory is fine for development and tests.
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "django_cache"}
        if os.getenv("CACHE_BACKEND") == "database"
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

if not DEBUG:
    # TLS is terminated by the reverse proxy (Caddy), which sets X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Application limits.
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
MAX_PATTERN_LENGTH = 1000
MAX_REPLACEMENT_LENGTH = 1000
# Total time budget for running one pattern over a dataset (guards against ReDoS).
REGEX_TIMEOUT_SECONDS = float(os.getenv("REGEX_TIMEOUT_SECONDS", "5"))
PREVIEW_SAMPLE_SIZE = 20
MAX_INSTRUCTION_LENGTH = 1000

# LLM (Claude). The Anthropic SDK reads ANTHROPIC_API_KEY from the environment.
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "medium")  # low | medium | high | xhigh | max
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
# Attempts per request, including self-correction retries after an unusable pattern.
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "2"))
# Distinct example values per column sent to the LLM as context.
LLM_SAMPLE_VALUES = 5

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
