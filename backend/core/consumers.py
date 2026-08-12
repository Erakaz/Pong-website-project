"""Consumer de diagnostic.

Sert a prouver que la chaine complete navigateur -> nginx -> Daphne fonctionne
en wss, independamment du jeu et du chat. Utilise dans la checklist
d'evaluation et dans le healthcheck manuel du README.
"""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class PingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        await self.accept()
        await self.send_json({"type": "ready"})

    async def receive_json(self, content: dict, **kwargs) -> None:
        # Aucune donnee applicative ne transite ici : on ne renvoie qu'un
        # accuse de reception, jamais le contenu recu.
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self.send_json({"type": "error", "code": "unknown_message"})
