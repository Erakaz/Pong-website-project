"""API REST du jeu."""

from __future__ import annotations

from django.db.models import Q

from core.http import (ApiError, json_ok, login_required, paginate, read_json,
                       require_methods)
from core.validation import (field_choice, field_int, field_str, validate_alias)
from game import bracket, engine, rooms, services, stats
from game.models import Match, Tournament



@require_methods("GET", "POST")
def matches(request):
    if request.method == "POST":
        return _create_match(request)
    return _list_matches(request)


def _list_matches(request):
    """Parties a distance ouvertes, ou historique d'un tournoi."""
    queryset = Match.objects.select_related("player1", "player2")

    state = request.GET.get("state")
    if state in dict(Match.STATE_CHOICES):
        queryset = queryset.filter(state=state)
    else:
        queryset = queryset.filter(state__in=[Match.STATE_LOBBY, Match.STATE_RUNNING])

    if request.GET.get("mode") in dict(Match.MODE_CHOICES):
        queryset = queryset.filter(mode=request.GET["mode"])

    queryset = queryset.exclude(mode=Match.MODE_LOCAL)

    items, meta = paginate(queryset, request)
    return json_ok({
        "matches": [match.to_dict(viewer=request.user) for match in items],
        "meta": meta,
    })


def _create_match(request):
    data = read_json(request)
    mode = field_choice(data, "mode", [Match.MODE_LOCAL, Match.MODE_REMOTE],
                        required=False, default=Match.MODE_LOCAL)
    points_to_win = field_int(data, "points_to_win", required=False,
                              default=engine.DEFAULT_POINTS_TO_WIN,
                              minimum=engine.MIN_POINTS_TO_WIN,
                              maximum=engine.MAX_POINTS_TO_WIN)

    if mode == Match.MODE_REMOTE:
        if not request.user.is_authenticated:
            raise ApiError("unauthorized",
                           "Il faut etre connecte pour ouvrir une partie a distance.", 401)
        match = services.create_remote_match(user=request.user, points_to_win=points_to_win)
        return json_ok({"match": match.to_dict(viewer=request.user)}, status=201)

    default_left = request.user.display_name if request.user.is_authenticated else "Joueur 1"
    alias1 = validate_alias(field_str(data, "alias1", required=False, default=default_left,
                                      max_len=24))
    alias2 = validate_alias(field_str(data, "alias2", required=False, default="Joueur 2",
                                      max_len=24))

    user = request.user if request.user.is_authenticated else None
    match = services.create_local_match(alias1=alias1, alias2=alias2,
                                        points_to_win=points_to_win, user=user)
    return json_ok({"match": match.to_dict(viewer=request.user)}, status=201)


@require_methods("GET")
def match_detail(request, match_id):
    match = _get_match(match_id)
    payload = {"match": match.to_dict(viewer=request.user), "geometry": engine.geometry()}

    room = rooms.registry.get(match_id)
    if room is not None:
        payload["state"] = room.engine.snapshot()
    return json_ok(payload)


@require_methods("GET")
def match_state(request, match_id):
    """Instantane courant — c'est la route que lit un client en ligne de commande."""
    room = rooms.registry.get(match_id)
    if room is None:
        match = _get_match(match_id)
        if match.state == Match.STATE_FINISHED:
            return json_ok({
                "status": engine.STATUS_FINISHED,
                "scores": [match.score1, match.score2],
                "winner": match.winner_side,
            })
        raise ApiError("not_running", "Cette partie n'est pas en cours.", 409)
    return json_ok(room.engine.snapshot())


@require_methods("POST")
def match_input(request, match_id):
    """Commande de raquette envoyee en HTTP (equivalent du message WebSocket)."""
    data = read_json(request)
    side = field_int(data, "side", minimum=engine.LEFT, maximum=engine.RIGHT)
    direction = field_int(data, "dir", minimum=-1, maximum=1)

    match = _get_match(match_id)
    room = rooms.registry.get(match_id)
    if room is None:
        raise ApiError("not_running", "Cette partie n'est pas en cours.", 409)

    if match.mode == Match.MODE_REMOTE:
        if match.side_of_user(request.user) != side:
            raise ApiError("forbidden_side", "Cette raquette ne t'appartient pas.", 403)

    room.engine.set_input(side, direction)
    return json_ok({"ok": True, "side": side, "dir": direction})


@require_methods("POST")
@login_required
def match_join(request, match_id):
    match = services.join_remote_match(match_id, request.user)
    return json_ok({"match": match.to_dict(viewer=request.user)})



@require_methods("GET")
@login_required
def dashboard(request):
    """Tableau de bord d'un joueur : le sien, ou celui d'un autre."""
    target = request.user
    if request.GET.get("user"):
        from accounts.models import User

        target = User.objects.filter(pk=request.GET["user"], is_active=True).first()
        if target is None:
            raise ApiError("not_found", "Ce joueur n'existe pas.", 404)

    return json_ok({
        "user": target.public_dict(),
        "summary": stats.summary(target),
        "by_opponent": stats.by_opponent(target),
        "recent_form": stats.recent_form(target),
        "history": stats.history(target, limit=20),
    })


@require_methods("GET")
@login_required
def match_dashboard(request, match_id):
    """Tableau de bord d'une partie : deroule du score et statistiques."""
    return json_ok(stats.match_detail(_get_match(match_id)))



@require_methods("GET", "POST")
def tournaments(request):
    if request.method == "POST":
        return _create_tournament(request)

    queryset = (Tournament.objects
                .filter(Q(state=Tournament.STATE_REGISTRATION) | Q(state=Tournament.STATE_RUNNING))
                .filter(mode=Tournament.MODE_REMOTE)
                .prefetch_related("players__user"))
    items, meta = paginate(queryset, request)
    return json_ok({
        "tournaments": [item.to_dict(include_bracket=False) for item in items],
        "meta": meta,
    })


def _create_tournament(request):
    data = read_json(request)
    name = field_str(data, "name", required=False, default="Tournoi", min_len=0, max_len=40)
    mode = field_choice(data, "mode", [Tournament.MODE_LOCAL, Tournament.MODE_REMOTE],
                        required=False, default=Tournament.MODE_LOCAL)
    points_to_win = field_int(data, "points_to_win", required=False,
                              default=engine.DEFAULT_POINTS_TO_WIN,
                              minimum=engine.MIN_POINTS_TO_WIN,
                              maximum=engine.MAX_POINTS_TO_WIN)
    user = request.user if request.user.is_authenticated else None

    if mode == Tournament.MODE_REMOTE:
        if user is None:
            raise ApiError("unauthorized",
                           "Il faut etre connecte pour ouvrir un tournoi a distance.", 401)
        alias = validate_alias(field_str(data, "alias", required=False,
                                         default=user.display_name, max_len=24))
        entries = [{"user": user, "alias": alias}]
    else:
        entries = _parse_aliases(data)

    tournament = services.create_tournament(
        name=name or "Tournoi", mode=mode, points_to_win=points_to_win,
        entries=entries, creator=user,
    )
    return json_ok({"tournament": tournament.to_dict(viewer=request.user)}, status=201)


def _parse_aliases(data: dict) -> list[dict]:
    """Alias saisis a l'ouverture d'un tournoi local."""
    raw = data.get("aliases")
    if not isinstance(raw, list):
        raise ApiError("missing_field", "La liste « aliases » est obligatoire.", 400,
                       {"field": "aliases"})
    if not (bracket.MIN_PLAYERS <= len(raw) <= bracket.MAX_PLAYERS):
        raise ApiError("invalid_player_count",
                       f"Un tournoi compte de {bracket.MIN_PLAYERS} a {bracket.MAX_PLAYERS} "
                       f"joueurs.", 400, {"field": "aliases"})

    entries, seen = [], set()
    for value in raw:
        if not isinstance(value, str):
            raise ApiError("invalid_alias", "Chaque alias doit etre une chaine.", 400,
                           {"field": "aliases"})
        alias = validate_alias(value)
        if alias.casefold() in seen:
            raise ApiError("duplicate_alias",
                           f"L'alias « {alias} » apparait deux fois.", 400,
                           {"field": "aliases"})
        seen.add(alias.casefold())
        entries.append({"user": None, "alias": alias})
    return entries


@require_methods("GET")
def tournament_detail(request, tournament_id):
    tournament = _get_tournament(tournament_id)
    return json_ok({"tournament": tournament.to_dict(viewer=request.user)})


@require_methods("POST")
@login_required
def tournament_join(request, tournament_id):
    data = read_json(request)
    alias = validate_alias(field_str(data, "alias", required=False,
                                     default=request.user.display_name, max_len=24))
    tournament = services.join_tournament(tournament_id, user=request.user, alias=alias)
    return json_ok({"tournament": tournament.to_dict(viewer=request.user)})


@require_methods("POST")
def tournament_start(request, tournament_id):
    tournament = _get_tournament(tournament_id)
    if tournament.mode == Tournament.MODE_REMOTE:
        if not request.user.is_authenticated or tournament.created_by_id != request.user.pk:
            raise ApiError("forbidden", "Seul l'organisateur peut lancer ce tournoi.", 403)
    tournament = services.start_tournament(tournament)
    return json_ok({"tournament": tournament.to_dict(viewer=request.user)})



def _get_match(match_id) -> Match:
    match = (Match.objects
             .select_related("player1", "player2", "tournament")
             .filter(pk=match_id)
             .first())
    if match is None:
        raise ApiError("not_found", "Cette partie n'existe pas.", 404)
    return match


def _get_tournament(tournament_id) -> Tournament:
    tournament = (Tournament.objects
                  .prefetch_related("players__user", "matches__player1", "matches__player2")
                  .filter(pk=tournament_id)
                  .first())
    if tournament is None:
        raise ApiError("not_found", "Ce tournoi n'existe pas.", 404)
    return tournament
