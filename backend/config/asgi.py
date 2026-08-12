"""Point d'entree ASGI : un seul process sert HTTP et WebSocket.

L'ordre des imports compte. `get_asgi_application()` doit etre appele avant
d'importer le moindre consumer, sinon les modeles sont touches avant que le
registre d'applications de Django ne soit pret (AppRegistryNotReady).
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from config.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # AllowedHostsOriginValidator rejette toute poignee de main WebSocket
        # dont l'en-tete Origin n'est pas dans ALLOWED_HOSTS. C'est l'equivalent
        # d'une protection CSRF pour les WebSockets : sans elle, n'importe quel
        # site tiers pourrait ouvrir une socket au nom d'un visiteur connecte.
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)
