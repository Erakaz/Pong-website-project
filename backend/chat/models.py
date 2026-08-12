"""Messagerie directe et blocages.

Le sujet demande cinq choses de ce module : envoyer des messages directs,
bloquer quelqu'un, inviter a jouer depuis la conversation, etre prevenu par le
systeme de tournoi, et acceder au profil d'un joueur depuis le chat. Les trois
premieres passent par ces modeles ; les deux autres sont du ressort du socket
de session et du frontend.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Message(models.Model):
    KIND_TEXT = "text"
    KIND_INVITE = "invite"          # invitation a une partie
    KIND_SYSTEM = "system"          # annonce du systeme de tournoi
    KIND_CHOICES = [
        (KIND_TEXT, "Message"),
        (KIND_INVITE, "Invitation"),
        (KIND_SYSTEM, "Systeme"),
    ]

    # Identifiant sequentiel, contrairement aux matchs qui utilisent un UUID :
    # un message n'est jamais adressable par URL, et un entier croissant
    # departage de facon fiable deux messages ecrits dans la meme microseconde
    # — ce qu'un UUID aleatoire ne permet pas.
    # `SET_NULL` et non `CASCADE` : supprimer un compte ne doit pas effacer la
    # moitie des conversations de ses interlocuteurs. Le contenu, lui, est
    # neutralise par la procedure RGPD.
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                               null=True, related_name="messages_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="messages_received")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=KIND_TEXT)
    body = models.TextField(max_length=1000, blank=True, default="")
    # Renseigne pour une invitation : la partie a rejoindre.
    match = models.ForeignKey("game.Match", on_delete=models.SET_NULL,
                              null=True, blank=True, related_name="invitations")
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_message"
        ordering = ["created_at", "id"]
        indexes = [
            # L'index qui porte l'affichage d'une conversation.
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
    """« The user should be able to block other users. »

    Le blocage est unidirectionnel et applique cote serveur : un message venant
    d'une personne bloquee n'est ni enregistre ni livre. Filtrer cote client
    serait cosmetique — il suffirait d'ouvrir les outils de developpement pour
    revoir les messages.
    """

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
