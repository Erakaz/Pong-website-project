"""Droits RGPD : acces, portabilite, anonymisation, effacement.

Le module « GDPR Compliance Options » demande quatre choses : consulter et
exporter ses donnees, les modifier, demander leur anonymisation, et supprimer
definitivement son compte. Les trois dernieres sont ici ; la modification passe
par les routes de profil habituelles.

Distinction importante entre les deux gestes destructeurs :

* **anonymiser** conserve la ligne du compte mais efface tout ce qui identifie
  la personne. Les matchs joues restent dans l'historique de ses adversaires,
  sous un nom neutre : leurs statistiques ne sont pas faussees par une
  disparition, et plus rien ne remonte a la personne ;
* **supprimer** efface la ligne. Il faut alors nettoyer AUSSI les traces
  laissees ailleurs — les alias figes sur les matchs, le contenu des messages
  envoyes — sinon un nom resterait lisible dans la base apres l'effacement.

Les deux operations sont irreversibles et se font dans une seule transaction.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from accounts.models import BackupCode, Friendship, RefreshToken, User
from chat.models import Block, Message
from game.models import Match, TournamentPlayer

logger = logging.getLogger(__name__)


def export(user: User) -> dict:
    """Toutes les donnees detenues sur cette personne, en JSON.

    C'est le droit d'acces et de portabilite : un format structure, lisible par
    un humain comme par un programme.
    """
    from game import stats

    matches = Match.objects.filter(player1=user) | Match.objects.filter(player2=user)

    return {
        "exported_at": timezone.now().isoformat(),
        "account": {
            "id": user.pk,
            "email": user.email,
            "display_name": user.display_name,
            "language": user.language,
            "date_joined": user.date_joined.isoformat(),
            "last_seen": user.last_seen.isoformat() if user.last_seen else None,
            "two_factor_enabled": user.totp_enabled,
            "oauth42_login": user.oauth42_login or None,
            "avatar": user.avatar.name if user.avatar else None,
            # Ni le mot de passe, ni son empreinte, ni le secret TOTP : les
            # exporter creerait un fichier dont la fuite compromettrait le
            # compte.
        },
        "statistics": stats.summary(user),
        "matches": [
            {
                "id": str(match.id),
                "played_at": match.finished_at.isoformat() if match.finished_at else None,
                "mode": match.mode,
                "opponent": match.alias_of(1 - (match.side_of_user(user) or 0)),
                "scores": [match.score1, match.score2],
                "your_side": match.side_of_user(user),
                "winner_side": match.winner_side,
            }
            for match in matches.distinct().order_by("-created_at")
        ],
        "tournaments": [
            {
                "id": str(entry.tournament_id),
                "name": entry.tournament.name,
                "alias": entry.alias,
                "eliminated": entry.eliminated,
                "joined_at": entry.joined_at.isoformat(),
            }
            for entry in TournamentPlayer.objects.filter(user=user).select_related("tournament")
        ],
        "messages_sent": [
            {
                "to": message.recipient.display_name if message.recipient else None,
                "body": message.body,
                "sent_at": message.created_at.isoformat(),
            }
            for message in Message.objects.filter(sender=user).select_related("recipient")
        ],
        "friends": [
            link.other(user).display_name
            for link in Friendship.objects.filter(status=Friendship.ACCEPTED)
            .filter(from_user=user).union(
                Friendship.objects.filter(status=Friendship.ACCEPTED, to_user=user))
        ],
        "blocked_users": [
            block.blocked.display_name
            for block in Block.objects.filter(blocker=user).select_related("blocked")
        ],
    }


def _anonymous_label(user: User) -> str:
    """Nom neutre, stable et unique, derive de la cle primaire."""
    return f"joueur_supprime_{user.pk}"


def _scrub_traces(user: User, label: str) -> None:
    """Efface les donnees personnelles disseminees hors de la ligne du compte."""
    # Alias figes sur les matchs : ce sont des noms lisibles, donc des donnees
    # personnelles, meme si la cle etrangere disparait.
    Match.objects.filter(player1=user).update(player1_alias=label)
    Match.objects.filter(player2=user).update(player2_alias=label)
    TournamentPlayer.objects.filter(user=user).update(alias=label)

    # Contenu des messages envoyes. Les lignes sont conservees pour ne pas
    # trouer les conversations des autres, mais elles ne disent plus rien.
    Message.objects.filter(sender=user).update(body="")

    # Relations : elles ne concernent plus personne.
    Friendship.objects.filter(from_user=user).delete()
    Friendship.objects.filter(to_user=user).delete()
    Block.objects.filter(blocker=user).delete()
    Block.objects.filter(blocked=user).delete()

    # Sessions et facteurs d'authentification.
    RefreshToken.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()

    if user.avatar:
        try:
            user.avatar.delete(save=False)
        except OSError:
            logger.warning("Avatar du compte %s introuvable a la suppression", user.pk)


@transaction.atomic
def anonymize(user: User) -> User:
    """Retire toute donnee identifiante en conservant la ligne du compte."""
    if user.is_anonymized:
        return user

    label = _anonymous_label(user)
    _scrub_traces(user, label)

    user.display_name = label
    user.email = None                 # unique mais nullable : plusieurs NULL possibles
    user.avatar = None
    user.oauth42_id = None
    user.oauth42_login = ""
    user.totp_secret = ""
    user.totp_enabled = False
    user.language = "fr"
    user.last_seen = None
    user.is_anonymized = True
    user.anonymized_at = timezone.now()
    # Sans e-mail, la connexion est impossible : le compte devient inerte.
    user.is_active = False
    user.set_unusable_password()
    # Invalide immediatement tout jeton encore en circulation.
    user.token_version += 1
    user.save()

    logger.info("Compte %s anonymise", user.pk)
    return user


@transaction.atomic
def delete_account(user: User) -> None:
    """Supprime definitivement le compte et tout ce qui s'y rattache."""
    user_id = user.pk
    _scrub_traces(user, f"joueur_supprime_{user_id}")
    user.delete()
    logger.info("Compte %s supprime definitivement", user_id)
