"""Configuration Django de ft_transcendence.

Tout ce qui est sensible ou dependant de l'environnement vient de variables
d'environnement (fichier `.env`, ignore par git). Aucun secret n'est ecrit en
dur dans ce fichier : le sujet sanctionne la publication de credentials par un
echec du projet.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
#  Lecture de l'environnement
# ---------------------------------------------------------------------------

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


# Vrai pendant `manage.py test` : permet d'eviter les dependances externes
# (Redis) dans la suite de tests.
TESTING = "test" in sys.argv


# ---------------------------------------------------------------------------
#  Base
# ---------------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-key-for-tests-only" if TESTING else None,
                     required=not TESTING)

# Garde-fou : refuser de demarrer en production avec les valeurs du modele.
if not DEBUG and not TESTING and SECRET_KEY.startswith("change-me"):
    raise RuntimeError(
        "DJANGO_SECRET_KEY vaut encore la valeur du modele. Lancer `make secrets`."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Origine publique du site (schema + hote + port), utilisee pour les cookies,
# les redirections OAuth et la validation d'Origin des WebSockets.
SITE_ORIGIN = env_str("SITE_ORIGIN", "https://localhost:8443").rstrip("/")

CSRF_TRUSTED_ORIGINS = [SITE_ORIGIN]

# nginx termine le TLS ; c'est cet en-tete qui apprend a Django que la requete
# d'origine etait bien en HTTPS (request.is_secure()).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# La redirection HTTP -> HTTPS et HSTS sont faits par nginx, en amont : les
# refaire ici provoquerait une double redirection.
SECURE_SSL_REDIRECT = False

USE_X_FORWARDED_HOST = True

# `manage.py check --deploy` signale l'absence de trois middlewares Django.
# Chacun est remplace par un mecanisme equivalent, place plus haut dans la
# chaine ; les activer en plus produirait des en-tetes en double.
SILENCED_SYSTEM_CHECKS = [
    # W001 SecurityMiddleware : HSTS, nosniff, Referrer-Policy et COOP sont
    # poses par nginx, seule voie d'entree du site (voir nginx/nginx.conf).
    "security.W001",
    # W002 X-Frame-Options : remplace par `frame-ancestors 'none'` dans la CSP,
    # qui a la priorite sur cet en-tete dans les navigateurs modernes.
    "security.W002",
    # W003 CsrfViewMiddleware : l'API s'authentifie par jeton porteur, donc
    # immunisee par construction. Le seul endpoint authentifie par cookie
    # (/api/auth/refresh) est protege par SameSite=Strict et une double
    # soumission maison (accounts/tokens.py).
    "security.W003",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = None  # Le projet est 100 % ASGI (HTTP + WebSocket).

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

APPEND_SLASH = False  # L'API expose des chemins sans slash final.


# ---------------------------------------------------------------------------
#  Applications
# ---------------------------------------------------------------------------
# `admin`, `sessions`, `messages` et `staticfiles` sont volontairement absents :
#   - pas d'admin      -> une surface d'attaque en moins, et rien dans le sujet
#                         ne la demande ;
#   - pas de sessions  -> l'authentification passe par des JWT (module 2FA/JWT) ;
#   - pas de staticfiles -> nginx sert directement le frontend statique.

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
    # En tete : une requete rejetee par le quota ne doit consommer ni requete
    # SQL, ni calcul de hachage.
    "core.middleware.RateLimitMiddleware",
    "core.middleware.JsonErrorMiddleware",
    "django.middleware.common.CommonMiddleware",
    "accounts.middleware.JWTAuthenticationMiddleware",
]

TEMPLATES = [
    {
        # Aucun template applicatif : l'API ne renvoie que du JSON et le
        # frontend est servi par nginx. Ce backend n'est declare que parce que
        # Django exige un moteur configure pour ses pages d'erreur internes.
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": False,
        "OPTIONS": {"context_processors": []},
    },
]


# ---------------------------------------------------------------------------
#  Base de donnees — PostgreSQL (impose par le module « Database »)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Redis — channel layer, presence en ligne, compteurs de rate-limit
# ---------------------------------------------------------------------------

REDIS_HOST = env_str("REDIS_HOST", "redis")
REDIS_PORT = env_int("REDIS_PORT", 6379)
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

if TESTING:
    # La suite de tests ne doit dependre d'aucun service externe.
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [(REDIS_HOST, REDIS_PORT)], "capacity": 512},
        }
    }


# ---------------------------------------------------------------------------
#  Authentification
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

# Argon2id en tete : c'est l'algorithme recommande par l'OWASP et le « strong
# password hashing algorithm » exige par le sujet. Les autres entrees ne
# servent qu'a rehacher automatiquement d'anciens mots de passe.
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

# --- JWT (module « 2FA + JWT ») --------------------------------------------
# Signature HS256 implementee a la main (accounts/jwt_utils.py) : ecrire le
# JWT est precisement l'objet du module, une bibliotheque le contournerait.
JWT_SECRET = env_str("JWT_SECRET", SECRET_KEY)
JWT_ISSUER = "ft_transcendence"
JWT_ACCESS_TTL = env_int("JWT_ACCESS_TTL", 900)          # 15 min
JWT_REFRESH_TTL = env_int("JWT_REFRESH_TTL", 1_209_600)  # 14 jours
# Jeton intermediaire delivre entre le mot de passe et le code 2FA.
JWT_TWOFA_TTL = 300                                      # 5 min

# Le refresh token vit dans un cookie httpOnly (invisible du JavaScript, donc
# hors de portee d'une XSS) ; l'access token, lui, ne quitte jamais la memoire
# de l'onglet.
REFRESH_COOKIE_NAME = "ftt_refresh"
# Cookie lisible par le JS, renvoye en en-tete X-CSRF-Token : double soumission
# qui protege l'endpoint de refresh, seul endpoint authentifie par cookie.
CSRF_COOKIE_NAME = "ftt_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

# --- OAuth 2.0 42 (module « Remote authentication ») ------------------------
# Vide = module desactive proprement : bouton masque cote frontend, 503 cote
# API. Aucun autre comportement ne change.
OAUTH42_UID = env_str("OAUTH42_UID", "")
OAUTH42_SECRET = env_str("OAUTH42_SECRET", "")
OAUTH42_REDIRECT_URI = env_str("OAUTH42_REDIRECT_URI", f"{SITE_ORIGIN}/api/auth/oauth42/callback")
OAUTH42_AUTHORIZE_URL = "https://api.intra.42.fr/oauth/authorize"
OAUTH42_TOKEN_URL = "https://api.intra.42.fr/oauth/token"
OAUTH42_ME_URL = "https://api.intra.42.fr/v2/me"
OAUTH42_ENABLED = bool(OAUTH42_UID and OAUTH42_SECRET)


# ---------------------------------------------------------------------------
#  Fichiers televerses (avatars)
# ---------------------------------------------------------------------------

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# nginx refuse deja les corps > 2 Mo ; on refuse aussi cote applicatif pour ne
# jamais dependre d'une seule couche de defense.
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_DIMENSION = 512
DATA_UPLOAD_MAX_MEMORY_SIZE = AVATAR_MAX_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = AVATAR_MAX_BYTES
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100

FILE_UPLOAD_PERMISSIONS = 0o644


# ---------------------------------------------------------------------------
#  Rate limiting (durcissement des routes d'authentification)
# ---------------------------------------------------------------------------
# (quota, fenetre en secondes) par adresse IP.
RATE_LIMITS = {
    "login": (10, 300),
    "register": (5, 3600),
    "twofa": (10, 300),
    "refresh": (60, 300),
}

if TESTING:
    # Desactive par defaut dans la suite de tests : des dizaines de cas se
    # connectent depuis la meme adresse et se bloqueraient mutuellement. Les
    # tests du quota lui-meme le reactivent via `override_settings`.
    RATE_LIMITS = {}


# ---------------------------------------------------------------------------
#  Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False   # Les traductions de l'interface sont gerees cote frontend.
USE_TZ = True


# ---------------------------------------------------------------------------
#  Journalisation — tout sur stdout, capture par `docker compose logs`
# ---------------------------------------------------------------------------

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
        # Daphne annonce chaque connexion WebSocket : trop verbeux en INFO.
        "daphne.http_protocol": {"level": "WARNING"},
        "django.db.backends": {"level": "WARNING"},
    },
}
