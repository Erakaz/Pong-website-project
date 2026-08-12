"""Limitation de debit sur les routes sensibles.

Sans elle, rien n'empeche d'essayer des milliers de mots de passe : Argon2
ralentit chaque tentative, mais un attaquant patient finit par passer sur un
mot de passe faible. Le quota par adresse IP transforme une attaque de quelques
heures en une attaque de plusieurs annees.

Compteur a fenetre fixe : une cle Redis par (route, IP) avec une expiration
egale a la fenetre. C'est le compromis habituel — moins precis qu'une fenetre
glissante, mais deux commandes Redis par requete et aucune structure a purger.

Redis indisponible ne doit jamais empecher quiconque de se connecter : on
retombe alors sur un compteur en memoire du process, qui protege deja de
l'essentiel puisque le projet ne fait tourner qu'un conteneur applicatif.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_redis_client = None
_redis_broken_until = 0.0
_memory: dict[str, tuple[int, float]] = {}


def _redis():
    """Client Redis partage, avec mise en quarantaine apres une panne."""
    global _redis_client, _redis_broken_until

    if time.monotonic() < _redis_broken_until:
        return None
    if _redis_client is not None:
        return _redis_client

    try:
        import redis

        _redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                                    socket_timeout=0.2, socket_connect_timeout=0.2)
        _redis_client.ping()
        return _redis_client
    except Exception:
        # Inutile de reessayer a chaque requete : on attend 30 secondes.
        logger.warning("Redis indisponible : rate-limit en memoire du process")
        _redis_client = None
        _redis_broken_until = time.monotonic() + 30
        return None


def _hit_memory(key: str, window: int) -> int:
    now = time.monotonic()
    count, expires = _memory.get(key, (0, 0.0))
    if now >= expires:
        count, expires = 0, now + window
    count += 1
    _memory[key] = (count, expires)

    # Purge opportuniste : sans elle, la table grandirait indefiniment.
    if len(_memory) > 4096:
        for stale in [k for k, (_, exp) in _memory.items() if exp <= now]:
            _memory.pop(stale, None)
    return count


def hit(bucket: str, identity: str) -> tuple[bool, int]:
    """Compte une tentative. Retourne (autorise, secondes avant reessai)."""
    limit, window = settings.RATE_LIMITS.get(bucket, (0, 0))
    if not limit:
        return True, 0

    key = f"ratelimit:{bucket}:{identity}"
    client = _redis()

    if client is not None:
        try:
            pipeline = client.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, window, nx=True)
            count = pipeline.execute()[0]
        except Exception:
            logger.warning("Rate-limit Redis en echec, bascule en memoire")
            count = _hit_memory(key, window)
    else:
        count = _hit_memory(key, window)

    return (count <= limit), window


def reset() -> None:
    """Remet tous les compteurs a zero. Reserve aux tests.

    Vide le compteur en memoire ET les cles Redis : sans le second, une suite
    de tests qui tourne avec Redis disponible voit ses cas se bloquer les uns
    les autres, alors que la meme suite passe sans Redis.
    """
    _memory.clear()
    client = _redis()
    if client is None:
        return
    try:
        for key in client.scan_iter(match="ratelimit:*", count=500):
            client.delete(key)
    except Exception:
        logger.warning("Purge des compteurs Redis impossible")


def client_identity(request) -> str:
    """Adresse de l'appelant, telle que nginx la transmet.

    `X-Forwarded-For` n'est digne de confiance que parce que la seule voie
    d'entree est notre propre reverse proxy, qui la reecrit. Exposer Daphne
    directement rendrait cet en-tete falsifiable et le quota contournable.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.META.get("REMOTE_ADDR", "inconnu")[:45]
