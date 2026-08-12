"""Operations metier sur les matchs et les tournois.

Ces fonctions sont synchrones et transactionnelles ; la boucle de jeu, qui est
asynchrone, les appelle via `database_sync_to_async`. Les regrouper ici evite
que la meme logique soit reecrite dans les vues HTTP et dans les consumers
WebSocket.
"""

from __future__ import annotations

import secrets

from django.db import transaction
from django.utils import timezone

from core.http import ApiError
from game import bracket, notifications
from game.models import Match, Tournament, TournamentPlayer


# ---------------------------------------------------------------------------
#  Matchs
# ---------------------------------------------------------------------------

def create_local_match(*, alias1: str, alias2: str, points_to_win: int,
                       user=None) -> Match:
    """Partie a deux sur le meme clavier — la partie obligatoire du sujet.

    Un seul navigateur pilote les deux raquettes ; la physique tourne malgre
    tout sur le serveur, exactement comme pour une partie a distance.
    """
    if alias1.casefold() == alias2.casefold():
        raise ApiError("duplicate_alias", "Les deux joueurs doivent avoir des alias differents.",
                       400, {"field": "alias2"})
    return Match.objects.create(
        mode=Match.MODE_LOCAL,
        state=Match.STATE_LOBBY,
        points_to_win=points_to_win,
        player1=user,
        player1_alias=alias1,
        player2_alias=alias2,
    )


def create_remote_match(*, user, points_to_win: int) -> Match:
    """Ouvre une partie a distance en attente d'un adversaire."""
    return Match.objects.create(
        mode=Match.MODE_REMOTE,
        state=Match.STATE_LOBBY,
        points_to_win=points_to_win,
        player1=user,
    )


@transaction.atomic
def join_remote_match(match_id, user) -> Match:
    """Rejoint une partie ouverte. Verrouille la ligne pour eviter que deux
    joueurs prennent la meme place au meme instant."""
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is None:
        raise ApiError("not_found", "Cette partie n'existe pas.", 404)
    if match.mode != Match.MODE_REMOTE:
        raise ApiError("not_joinable", "Cette partie n'est pas une partie a distance.", 400)
    if match.state != Match.STATE_LOBBY:
        raise ApiError("not_joinable", "Cette partie n'accepte plus de joueur.", 409)
    if match.player1_id == user.pk:
        raise ApiError("already_joined", "Tu es deja dans cette partie.", 409)
    if match.player2_id:
        raise ApiError("match_full", "Cette partie est complete.", 409)

    match.player2 = user
    match.save(update_fields=["player2"])
    return match


@transaction.atomic
def finish_match(match_id, snapshot: dict, stats: dict, *, forfeit: bool = False,
                 points_log: list | None = None) -> Match:
    """Fige le resultat puis fait progresser le tournoi si le match en fait partie.

    `of=("self",)` restreint le verrou a la ligne du match. Sans lui, PostgreSQL
    refuse la requete : `select_related("tournament")` produit un LEFT OUTER
    JOIN (le tournoi est facultatif), et un `SELECT ... FOR UPDATE` ne peut pas
    porter sur le cote nullable d'une jointure externe. SQLite, lui, ignore
    purement et simplement `FOR UPDATE` — d'ou une erreur invisible tant qu'on
    ne teste pas sur la vraie base.
    """
    match = (Match.objects
             .select_for_update(of=("self",))
             .select_related("tournament")
             .get(pk=match_id))
    if match.state == Match.STATE_FINISHED:
        return match          # deja enregistre (double appel possible a l'arret)

    match.record_result(snapshot, stats, forfeit=forfeit, points_log=points_log)
    if match.tournament_id:
        advance_tournament(match)
    return match


@transaction.atomic
def abort_match(match_id) -> None:
    """Abandonne une partie qui n'a jamais demarre (personne ne s'est connecte)."""
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match and match.state in (Match.STATE_LOBBY, Match.STATE_RUNNING):
        match.state = Match.STATE_ABORTED
        match.finished_at = timezone.now()
        match.save(update_fields=["state", "finished_at"])


# ---------------------------------------------------------------------------
#  Tournois
# ---------------------------------------------------------------------------

@transaction.atomic
def create_tournament(*, name: str, mode: str, points_to_win: int, entries: list[dict],
                      creator=None) -> Tournament:
    """Cree un tournoi.

    En mode local, tous les alias sont saisis d'un coup et le tableau est monte
    immediatement — c'est le deroulement decrit par le sujet (« at the start of
    a tournament, each player must input their alias name »). En mode a
    distance, `entries` ne contient que le createur et les autres rejoignent
    ensuite.
    """
    tournament = Tournament.objects.create(
        name=name,
        mode=mode,
        points_to_win=points_to_win,
        size=max(len(entries), bracket.MIN_PLAYERS),
        created_by=creator,
        state=Tournament.STATE_REGISTRATION,
    )
    for index, entry in enumerate(entries):
        TournamentPlayer.objects.create(
            tournament=tournament,
            user=entry.get("user"),
            alias=entry["alias"],
            seed_index=index,
        )

    if mode == Tournament.MODE_LOCAL:
        start_tournament(tournament)
    return tournament


@transaction.atomic
def join_tournament(tournament_id, *, user, alias: str) -> Tournament:
    tournament = Tournament.objects.select_for_update().filter(pk=tournament_id).first()
    if tournament is None:
        raise ApiError("not_found", "Ce tournoi n'existe pas.", 404)
    if tournament.state != Tournament.STATE_REGISTRATION:
        raise ApiError("registration_closed", "Les inscriptions sont fermees.", 409)
    if tournament.players.count() >= bracket.MAX_PLAYERS:
        raise ApiError("tournament_full",
                       f"Un tournoi ne peut pas depasser {bracket.MAX_PLAYERS} joueurs.", 409)
    if tournament.players.filter(user=user).exists():
        raise ApiError("already_registered", "Tu es deja inscrit a ce tournoi.", 409)
    if tournament.players.filter(alias__iexact=alias).exists():
        raise ApiError("duplicate_alias", "Cet alias est deja pris dans ce tournoi.", 409,
                       {"field": "alias"})

    TournamentPlayer.objects.create(
        tournament=tournament, user=user, alias=alias,
        seed_index=tournament.players.count(),
    )
    tournament.size = tournament.players.count()
    tournament.save(update_fields=["size"])
    return tournament


@transaction.atomic
def start_tournament(tournament: Tournament) -> Tournament:
    """Monte le tableau complet et ouvre la premiere rencontre."""
    if tournament.state != Tournament.STATE_REGISTRATION:
        raise ApiError("already_started", "Ce tournoi a deja commence.", 409)

    players = list(tournament.players.order_by("seed_index", "joined_at"))
    if len(players) < bracket.MIN_PLAYERS:
        raise ApiError("not_enough_players",
                       f"Il faut au moins {bracket.MIN_PLAYERS} joueurs pour lancer un tournoi.",
                       400)

    _materialize_bracket(tournament, players)

    tournament.size = len(players)
    tournament.state = Tournament.STATE_RUNNING
    tournament.started_at = timezone.now()
    tournament.save(update_fields=["size", "state", "started_at"])

    # Le systeme de tournoi annonce le prochain combat (exigence du module
    # « Live chat »).
    notifications.announce_next_match(tournament.next_match())
    return tournament


def _materialize_bracket(tournament: Tournament, players: list[TournamentPlayer]) -> None:
    """Cree d'un coup tous les matchs de tous les tours.

    Les rencontres futures existent des le depart, avec des cotes vides : le
    front peut donc afficher le tableau entier et l'ordre de passage, comme le
    sujet l'exige, plutot que de decouvrir les matchs au fur et a mesure.
    """
    count = len(players)
    size = bracket.bracket_size(count)
    total_rounds = bracket.rounds_count(count)

    matches: dict[tuple[int, int], Match] = {}
    for round_index in range(total_rounds):
        slots = size // (2 ** (round_index + 1))
        for slot_index in range(slots):
            matches[(round_index, slot_index)] = Match(
                tournament=tournament,
                mode=tournament.mode,
                state=Match.STATE_PENDING,
                points_to_win=tournament.points_to_win,
                round_index=round_index,
                slot_index=slot_index,
                seed=secrets.randbits(62),
            )

    for slot_index, (left, right) in enumerate(bracket.first_round_pairings(count)):
        if left is None or right is None:
            # Exemption : aucun match n'est joue, le joueur monte d'un tour.
            seed_index = left if right is None else right
            parent_round, parent_slot = bracket.parent_slot(0, slot_index)
            _seat(matches[(parent_round, parent_slot)],
                  bracket.parent_side(slot_index), players[seed_index])
            del matches[(0, slot_index)]
            continue

        match = matches[(0, slot_index)]
        _seat(match, Match.LEFT, players[left])
        _seat(match, Match.RIGHT, players[right])

    Match.objects.bulk_create(matches.values())


def _seat(match: Match, side: int, player: TournamentPlayer) -> None:
    # L'alias d'inscription est recopie sur le match : c'est sous ce nom que le
    # tableau affiche la rencontre, et il reste juste meme si le compte est
    # renomme plus tard.
    match.set_player(side, user=player.user, alias=player.alias)


def advance_tournament(match: Match) -> None:
    """Qualifie le vainqueur pour le tour suivant, ou sacre le champion."""
    tournament = match.tournament
    if tournament is None or match.winner_side is None:
        return

    winner = _tournament_player_for(tournament, match, match.winner_side)
    loser = _tournament_player_for(tournament, match, 1 - match.winner_side)
    if loser is not None and not loser.eliminated:
        loser.eliminated = True
        loser.save(update_fields=["eliminated"])
    if winner is None:
        return

    if match.round_index + 1 >= tournament.rounds_count:
        tournament.winner = winner
        tournament.state = Tournament.STATE_FINISHED
        tournament.finished_at = timezone.now()
        tournament.save(update_fields=["winner", "state", "finished_at"])
        return

    parent_round, parent_slot = bracket.parent_slot(match.round_index, match.slot_index)
    parent = tournament.matches.filter(round_index=parent_round,
                                       slot_index=parent_slot).first()
    if parent is None:
        return
    _seat(parent, bracket.parent_side(match.slot_index), winner)
    parent.save(update_fields=["player1", "player1_alias", "player2", "player2_alias", "state"])

    # Des que la rencontre suivante a ses deux joueurs, on les previent.
    notifications.announce_next_match(tournament.next_match())


def _tournament_player_for(tournament: Tournament, match: Match, side: int):
    """Retrouve l'inscrit correspondant a un cote du match.

    On cherche d'abord par compte : deux inscrits peuvent porter des alias
    proches, mais jamais le meme compte (contrainte d'unicite du modele).
    """
    user = match.user_of(side)
    if user is not None:
        found = tournament.players.filter(user=user).first()
        if found is not None:
            return found
    alias = match.alias_of(side)
    if not alias:
        return None
    return tournament.players.filter(alias=alias).first()
