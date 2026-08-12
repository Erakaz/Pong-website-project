"""Messagerie directe et blocages."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Message(models.Model):
    KIND_TEXT = "text"
    KIND_INVITE = "invite"
    KIND_SYSTEM = "system"
    KIND_CHOICES = [
        (KIND_TEXT, "Message"),
        (KIND_INVITE, "Invitation"),
        (KIND_SYSTEM, "Systeme"),
    ]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                               null=True, related_name="messages_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="messages_received")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=KIND_TEXT)
    body = models.TextField(max_length=1000, blank=True, default="")
    match = models.ForeignKey("game.Match", on_delete=models.SET_NULL,
                              null=True, blank=True, related_name="invitations")
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_message"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["recipient", "sender", "-created_at"]),
            models.Index(fields=["recipient", "read_at"]),
        ]

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "kind": self.kind,
            "body": self.body,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "match_id": str(self.match_id) if self.match_id else None,
            "created_at": self.created_at.isoformat(),
            "read": self.read_at is not None,
        }


class Block(models.Model):
    """« The user should be able to block other users. »"""

    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="blocks_made")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="blocks_received")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "chat_block"
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_block"),
            models.CheckConstraint(condition=~models.Q(blocker=models.F("blocked")),
                                   name="no_self_block"),
        ]
        indexes = [models.Index(fields=["blocker"])]
