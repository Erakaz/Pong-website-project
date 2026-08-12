"""Modeles du domaine « comptes ».

Choix d'identite documente (le sujet demande explicitement de justifier la
gestion des doublons de pseudo/email) :

* `email` est unique et sert d'ancre d'identite : c'est l'identifiant de
  connexion, et c'est lui qui permet de reconnaitre qu'un compte 42 et un
  compte mot de passe designent la meme personne ;
* `display_name` est unique separement : c'est le nom public, celui qui
  s'affiche en tournoi et dans le chat. Deux personnes ne peuvent pas porter le
  meme, sinon un tournoi devient illisible et l'usurpation devient triviale ;
* un compte anonymise (RGPD) libere son `display_name` et perd son `email`,
  d'ou `null=True` : PostgreSQL autorise plusieurs NULL dans un index unique.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


def avatar_upload_to(instance: "User", filename: str) -> str:
    """Nom de fichier aleatoire, extension fixe.

    Le nom fourni par le client n'est jamais reutilise : il pourrait contenir
    une traversee de chemin (`../../`) ou une double extension trompeuse. Le
    contenu est de toute facon re-encode en PNG avant ecriture.
    """
    return f"avatars/{uuid.uuid4().hex}.png"


class UserManager(BaseUserManager):
    """Manager minimal : pas d'admin Django, donc pas de `create_superuser`."""

    use_in_migrations = True

    def create_user(self, email: str, display_name: str, password: str | None = None,
                    **extra) -> "User":
        if not email:
            raise ValueError("Un compte doit avoir une adresse e-mail.")
        if not display_name:
            raise ValueError("Un compte doit avoir un pseudo.")
        user = self.model(email=self.normalize_email(email).lower(),
                          display_name=display_name, **extra)
        if password:
            user.set_password(password)
        else:
            # Compte cree via OAuth 42 : aucun mot de passe utilisable, mais
            # un hash inutilisable plutot qu'un champ vide, pour que
            # `check_password` echoue toujours en temps constant.
            user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=24, unique=True)
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    # Rafraichi par le heartbeat WebSocket ; sert de repli quand Redis a perdu
    # la cle de presence (redemarrage du conteneur).
    last_seen = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=5, default="fr")

    # --- Double authentification (module 2FA + JWT) ------------------------
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    totp_enabled = models.BooleanField(default=False)

    # --- Authentification distante 42 (module Remote authentication) -------
    oauth42_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    oauth42_login = models.CharField(max_length=64, blank=True, default="")

    # --- RGPD --------------------------------------------------------------
    is_anonymized = models.BooleanField(default=False)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    # Numero de generation des jetons. Chaque access token emis embarque cette
    # valeur ; l'incrementer invalide instantanement tous les jetons existants
    # (changement de mot de passe, activation de la 2FA, « se deconnecter
    # partout »), sans liste noire a maintenir.
    #
    # Un compteur plutot qu'une date : comparer un horodatage a la seconde
    # laissait survivre un jeton emis dans la meme seconde que la revocation.
    # Un entier ne souffre d'aucune granularite.
    token_version = models.PositiveIntegerField(default=0)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def avatar_url(self) -> str:
        """URL de l'avatar, ou l'avatar par defaut si aucun n'a ete televerse."""
        if self.avatar and self.avatar.name:
            return self.avatar.url
        return "/assets/default-avatar.svg"

    def public_dict(self) -> dict:
        """Vue publique : ce que n'importe quel utilisateur connecte peut voir."""
        return {
            "id": self.pk,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "is_anonymized": self.is_anonymized,
        }

    def private_dict(self) -> dict:
        """Vue privee : uniquement pour le proprietaire du compte."""
        return {
            **self.public_dict(),
            "email": self.email,
            "language": self.language,
            "totp_enabled": self.totp_enabled,
            "has_password": self.has_usable_password(),
            "oauth42_login": self.oauth42_login or None,
            "date_joined": self.date_joined.isoformat(),
        }

    def revoke_all_tokens(self) -> None:
        """Invalide immediatement tous les jetons deja emis pour ce compte.

        L'appelant qui souhaite garder la session courante ouverte doit emettre
        de nouveaux jetons APRES cet appel : ils porteront la nouvelle version.
        """
        self.token_version += 1
        self.save(update_fields=["token_version"])
        self.refresh_tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


class RefreshToken(models.Model):
    """Jeton de rafraichissement, rotatif et a usage unique.

    Seul le SHA-256 du jeton est stocke : une fuite de la base ne permet pas de
    rejouer les sessions, exactement comme pour un mot de passe. Le jeton clair
    n'existe que dans le cookie httpOnly du navigateur.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Renseigne quand ce jeton a ete echange contre un nouveau. Si un jeton
    # deja rotate est represente, c'est qu'il a fuite : toute la chaine est
    # alors revoquee (detection de rejeu).
    rotated_to = models.OneToOneField(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="rotated_from"
    )

    class Meta:
        db_table = "accounts_refresh_token"
        indexes = [models.Index(fields=["user", "revoked_at"])]

    def is_valid(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


class BackupCode(models.Model):
    """Code de secours a usage unique, pour reprendre la main sans son 2FA."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="backup_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(default=timezone.now)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_backup_code"
        indexes = [models.Index(fields=["user", "used_at"])]


class Friendship(models.Model):
    """Relation d'amitie, avec demande puis acceptation.

    Une seule ligne par paire : le sens (`from_user` -> `to_user`) ne sert
    qu'a savoir qui doit repondre a la demande.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    STATUS_CHOICES = [(PENDING, "En attente"), (ACCEPTED, "Acceptee")]

    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_sent")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name="friendships_received")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_friendship"
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="unique_friendship_pair"),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="no_self_friendship",
            ),
        ]
        indexes = [models.Index(fields=["to_user", "status"])]

    def other(self, user: User) -> User:
        return self.to_user if self.from_user_id == user.pk else self.from_user
