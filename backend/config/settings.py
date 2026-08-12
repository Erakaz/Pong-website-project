"""Configuration Django de ft_transcendence."""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent



def env_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}. "
            f"Copier .env.example en .env puis lancer `make secrets`."
        )
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


TESTING = "test" in sys.argv



DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-key-for-tests-only" if TESTING else None,
                     required=not TESTING)

if not DEBUG and not TESTING and SECRET_KEY.startswith("change-me"):
    raise RuntimeError(
        "DJANGO_SECRET_KEY vaut encore la valeur du modele. Lancer `make secrets`."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

SITE_ORIGIN = env_str("SITE_ORIGIN", "https://localhost:8443").rstrip("/")

CSRF_TRUSTED_ORIGINS = [SITE_ORIGIN]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False

USE_X_FORWARDED_HOST = True

SILENCED_SYSTEM_CHECKS = [
    "security.W001",
    "security.W002",
    "security.W003",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = None

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

APPEND_SLASH = False



INSTALLED_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "channels",
    "core",
    "accounts",
    "game",
    "chat",
]

MIDDLEWARE = [
    "core.middleware.RateLimitMiddleware",
    "core.middleware.JsonErrorMiddleware",
    "django.middleware.common.CommonMiddleware",
    "accounts.middleware.JWTAuthenticationMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": False,
        "OPTIONS": {"context_processors": []},
    },
]



DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "transcendence"),
        "USER": env_str("POSTGRES_USER", "transcendence"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", ""),
        "HOST": env_str("POSTGRES_HOST", "postgres"),
        "PORT": env_str("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}



REDIS_HOST = env_str("REDIS_HOST", "redis")
REDIS_PORT = env_int("REDIS_PORT", 6379)
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

if TESTING:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [(REDIS_HOST, REDIS_PORT)], "capacity": 512},
        }
    }



AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

JWT_SECRET = env_str("JWT_SECRET", SECRET_KEY)
JWT_ISSUER = "ft_transcendence"
JWT_ACCESS_TTL = env_int("JWT_ACCESS_TTL", 900)
JWT_REFRESH_TTL = env_int("JWT_REFRESH_TTL", 1_209_600)
JWT_TWOFA_TTL = 300

REFRESH_COOKIE_NAME = "ftt_refresh"
CSRF_COOKIE_NAME = "ftt_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

OAUTH42_UID = env_str("OAUTH42_UID", "")
OAUTH42_SECRET = env_str("OAUTH42_SECRET", "")
OAUTH42_REDIRECT_URI = env_str("OAUTH42_REDIRECT_URI", f"{SITE_ORIGIN}/api/auth/oauth42/callback")
OAUTH42_AUTHORIZE_URL = "https://api.intra.42.fr/oauth/authorize"
OAUTH42_TOKEN_URL = "https://api.intra.42.fr/oauth/token"
OAUTH42_ME_URL = "https://api.intra.42.fr/v2/me"
OAUTH42_ENABLED = bool(OAUTH42_UID and OAUTH42_SECRET)



MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_DIMENSION = 512
DATA_UPLOAD_MAX_MEMORY_SIZE = AVATAR_MAX_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = AVATAR_MAX_BYTES
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100

FILE_UPLOAD_PERMISSIONS = 0o644


RATE_LIMITS = {
    "login": (10, 300),
    "register": (5, 3600),
    "twofa": (10, 300),
    "refresh": (60, 300),
}

if TESTING:
    RATE_LIMITS = {}



LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True



LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": sys.stdout,
        },
    },
    "root": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO"},
    "loggers": {
        "daphne.http_protocol": {"level": "WARNING"},
        "django.db.backends": {"level": "WARNING"},
    },
}
