"""Table de routage WebSocket (wss:// uniquement, impose par le sujet)."""

from django.urls import path

from accounts.consumers import LiveConsumer
from core.consumers import PingConsumer
from game.consumers import MatchConsumer

websocket_urlpatterns = [
    path("ws/live", LiveConsumer.as_asgi()),

    path("ws/ping", PingConsumer.as_asgi()),

    path("ws/game/<uuid:match_id>", MatchConsumer.as_asgi()),
]
