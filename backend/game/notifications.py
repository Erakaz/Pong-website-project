"""Annonces du systeme de tournoi.

Le sujet l'exige explicitement dans le module « Live chat » : « the tournament
system should be able to warn users expected for the next game ». L'annonce
emprunte donc le meme canal que les messages directs — un message de type
`system` depose dans la boite aux lettres de chaque joueur concerne, puis
pousse en temps reel s'il est connecte.
"""

from __future__ import annotations

import logging

from chat import services as chat_services
from game.models import Match

logger = logging.getLogger(__name__)


def announce_next_match(match: Match) -> None:
    """Previent les deux joueurs qu'une rencontre les attend."""
    if match is None or not match.is_ready:
        return

    opponents = {Match.LEFT: Match.RIGHT, Match.RIGHT: Match.LEFT}
    for side, other_side in opponents.items():
        user = match.user_of(side)
        if user is None:
            continue          # joueur non inscrit : rien a notifier
        body = (f"C'est a toi de jouer : {match.alias_of(side)} contre "
                f"{match.alias_of(other_side)}.")
        try:
            message = chat_services.notify(user, body, match=match)
            _push(user.pk, message)
        except Exception:
            # Une notification perdue ne doit jamais faire echouer la
            # progression du tournoi, qui elle est deja enregistree.
            logger.exception("Annonce du prochain match impossible pour %s", user.pk)


def _push(user_id: int, message) -> None:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from accounts.consumers import user_group

    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(user_group(user_id), {
        "type": "live.chat",
        "message": message.to_dict(),
    })
