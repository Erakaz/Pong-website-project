"""Consumer de diagnostic."""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class PingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        await self.accept()
        await self.send_json({"type": "ready"})

    async def receive_json(self, content: dict, **kwargs) -> None:
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self.send_json({"type": "error", "code": "unknown_message"})
