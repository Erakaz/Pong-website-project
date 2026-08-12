"""Table de routage WebSocket (wss:// uniquement, impose par le sujet)."""

from django.urls import path

from accounts.consumers import LiveConsumer
from core.consumers import PingConsumer
from game.consumers import MatchConsumer

websocket_urlpatterns = [
    # Socket de session : presence en ligne et notifications. Une par onglet.
    path("ws/live", LiveConsumer.as_asgi()),

    # Sonde de connectivite : sert a verifier de bout en bout que la chaine
    # navigateur -> nginx -> Daphne fonctionne en wss, sans dependre du jeu.
    path("ws/ping", PingConsumer.as_asgi()),

    # Une partie de Pong. L'identifiant est un UUID : il n'est pas devinable,
    # contrairement a un entier auto-incremente.
    path("ws/game/<uuid:match_id>", MatchConsumer.as_asgi()),
]
