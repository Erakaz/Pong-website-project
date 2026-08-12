"""Matchs et tournois persistes."""

from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from game import engine


class Match(models.Model):
    MODE_LOCAL = "local"
    MODE_REMOTE = "remote"
    MODE_CHOICES = [(MODE_LOCAL, "Local"), (MODE_REMOTE, "A distance")]

    STATE_PENDING = "pending"
    STATE_LOBBY = "lobby"
    STATE_RUNNING = "running"
    STATE_FINISHED = "finished"
    STATE_ABORTED = "aborted"
    STATE_CHOICES = [
        (STATE_PENDING, "A determiner"),
        (STATE_LOBBY, "En attente"),
        (STATE_RUNNING, "En cours"),
        (STATE_FINISHED, "Terminee"),
        (STATE_ABORTED, "Abandonnee"),
    ]

    LEFT = engine.LEFT
    RIGHT = engine.RIGHT

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default=MODE_LOCAL)
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=STATE_LOBBY)
    points_to_win = models.PositiveSmallIntegerField(default=engine.DEFAULT_POINTS_TO_WIN)
    seed = models.BigIntegerField(default=0)

    player1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="matches_as_left")
    player1_alias = models.CharField(max_length=24, blank=True, default="")
    player2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="matches_as_right")
    player2_alias = models.CharField(max_length=24, blank=True, default="")

    score1 = models.PositiveSmallIntegerField(default=0)
    score2 = models.PositiveSmallIntegerField(default=0)
    winner_side = models.PositiveSmallIntegerField(null=True, blank=True)
    by_forfeit = models.BooleanField(default=False)

    tournament = models.ForeignKey("game.Tournament", on_delete=models.CASCADE,
                                   null=True, blank=True, related_name="matches")
    round_index = models.PositiveSmallIntegerField(default=0)
    slot_index = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    duration_seconds = models.FloatField(default=0.0)
    total_hits = models.PositiveIntegerField(default=0)
    longest_rally = models.PositiveIntegerField(default=0)
    points_log = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "game_match"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["state", "mode"]),
            models.Index(fields=["tournament", "round_index", "slot_index"]),
            models.Index(fields=["-finished_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.alias_of(self.LEFT)} vs {self.alias_of(self.RIGHT) or '?'}"

    def save(self, *args, **kwargs):
        if not self.seed:
            self.seed = secrets.randbits(62)
        super().save(*args, **kwargs)


    def user_of(self, side: int):
        return self.player1 if side == self.LEFT else self.player2

    def alias_of(self, side: int) -> str:
        """Nom affiche pour ce cote."""
        stored = self.player1_alias if side == self.LEFT else self.player2_alias
        if stored:
            return stored
        user = self.user_of(side)
        return user.display_name if user is not None else ""

    def side_of_user(self, user) -> int | None:
        """Retourne le cote occupe par cet utilisateur, ou None."""
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        if self.player1_id == user.pk:
            return self.LEFT
        if self.player2_id == user.pk:
            return self.RIGHT
        return None

    @property
    def is_full(self) -> bool:
        return bool(self.player2_id or self.player2_alias)

    @property
    def is_ready(self) -> bool:
        """Les deux cotes sont connus : la rencontre peut etre jouee."""
        return bool(self.player1_id or self.player1_alias) and self.is_full

    def set_player(self, side: int, *, user=None, alias: str = "") -> None:
        """Place un joueur sur un cote, et fait passer le match en lobby si complet."""
        if side == self.LEFT:
            self.player1, self.player1_alias = user, alias
        else:
            self.player2, self.player2_alias = user, alias
        if self.state == self.STATE_PENDING and self.is_ready:
            self.state = self.STATE_LOBBY


    def mark_started(self) -> None:
        self.state = self.STATE_RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["state", "started_at"])

    def record_result(self, snapshot: dict, stats: dict, *, forfeit: bool = False,
                      points_log: list | None = None) -> None:
        """Fige le resultat d'une partie terminee."""
        self.score1, self.score2 = snapshot["scores"]
        self.winner_side = snapshot["winner"]
        self.by_forfeit = forfeit
        self.state = self.STATE_FINISHED
        self.finished_at = timezone.now()
        self.duration_seconds = stats.get("duration_seconds", 0.0)
        self.total_hits = stats.get("total_hits", 0)
        self.longest_rally = stats.get("longest_rally", 0)
        self.points_log = points_log or []
        self.save(update_fields=[
            "score1", "score2", "winner_side", "by_forfeit", "state",
            "finished_at", "duration_seconds", "total_hits", "longest_rally",
            "points_log",
        ])


    def to_dict(self, *, viewer=None) -> dict:
        return {
            "id": str(self.id),
            "mode": self.mode,
            "state": self.state,
            "points_to_win": self.points_to_win,
            "players": [
                self._player_dict(self.LEFT),
                self._player_dict(self.RIGHT),
            ],
            "scores": [self.score1, self.score2],
            "winner_side": self.winner_side,
            "by_forfeit": self.by_forfeit,
            "tournament_id": str(self.tournament_id) if self.tournament_id else None,
            "round_index": self.round_index,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "total_hits": self.total_hits,
            "longest_rally": self.longest_rally,
            "your_side": self.side_of_user(viewer),
        }

    def _player_dict(self, side: int) -> dict:
        user = self.user_of(side)
        return {
            "alias": self.alias_of(side),
            "user_id": user.pk if user else None,
            "avatar_url": user.avatar_url if user else None,
        }


class Tournament(models.Model):
    STATE_REGISTRATION = "registration"
    STATE_RUNNING = "running"
    STATE_FINISHED = "finished"
    STATE_CHOICES = [
        (STATE_REGISTRATION, "Inscriptions"),
        (STATE_RUNNING, "En cours"),
        (STATE_FINISHED, "Termine"),
    ]

    MODE_LOCAL = Match.MODE_LOCAL
    MODE_REMOTE = Match.MODE_REMOTE

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=40)
    mode = models.CharField(max_length=8, choices=Match.MODE_CHOICES, default=MODE_LOCAL)
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STATE_REGISTRATION)
    size = models.PositiveSmallIntegerField(default=4)
    points_to_win = models.PositiveSmallIntegerField(default=engine.DEFAULT_POINTS_TO_WIN)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="tournaments_created")
    winner = models.ForeignKey("game.TournamentPlayer", on_delete=models.SET_NULL,
                               null=True, blank=True, related_name="won_tournaments")

    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "game_tournament"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["state", "-created_at"])]

    def __str__(self) -> str:
        return self.name

    @property
    def rounds_count(self) -> int:
        return max(1, (self.size - 1).bit_length())

    def to_dict(self, *, include_bracket: bool = True, viewer=None) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "mode": self.mode,
            "state": self.state,
            "size": self.size,
            "points_to_win": self.points_to_win,
            "rounds_count": self.rounds_count,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat(),
            "winner": self.winner.to_dict() if self.winner_id else None,
            "players": [player.to_dict() for player in self.players.all()],
        }
        if include_bracket:
            data["bracket"] = self.bracket_dict(viewer=viewer)
            data["next_match"] = self.next_match_dict(viewer=viewer)
        return data

    def bracket_dict(self, *, viewer=None) -> list[dict]:
        """Le bracket, tour par tour."""
        rounds: list[dict] = []
        matches = list(self.matches.select_related("player1", "player2")
                       .order_by("round_index", "slot_index"))
        for index in range(self.rounds_count):
            in_round = [match for match in matches if match.round_index == index]
            rounds.append({
                "index": index,
                "name": round_label(index, self.rounds_count),
                "matches": [match.to_dict(viewer=viewer) for match in in_round],
            })
        return rounds

    def next_match(self):
        """Prochaine rencontre a jouer, dans l'ordre du bracket."""
        return (self.matches
                .filter(state__in=[Match.STATE_LOBBY, Match.STATE_RUNNING])
                .order_by("round_index", "slot_index")
                .select_related("player1", "player2")
                .first())

    def next_match_dict(self, *, viewer=None) -> dict | None:
        match = self.next_match()
        return match.to_dict(viewer=viewer) if match else None


class TournamentPlayer(models.Model):
    """Un participant : soit un compte, soit un simple alias."""

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True, related_name="tournament_entries")
    alias = models.CharField(max_length=24)
    seed_index = models.PositiveSmallIntegerField(default=0)
    eliminated = models.BooleanField(default=False)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "game_tournament_player"
        ordering = ["seed_index", "joined_at"]
        constraints = [
            models.UniqueConstraint(fields=["tournament", "alias"],
                                    name="unique_alias_per_tournament"),
            models.UniqueConstraint(fields=["tournament", "user"],
                                    condition=models.Q(user__isnull=False),
                                    name="unique_user_per_tournament"),
        ]

    def __str__(self) -> str:
        return self.alias

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "alias": self.alias,
            "user_id": self.user_id,
            "avatar_url": self.user.avatar_url if self.user else None,
            "seed_index": self.seed_index,
            "eliminated": self.eliminated,
        }


def round_label(index: int, total: int) -> str:
    """Nom lisible d'un tour, compte a rebours depuis la finale."""
    remaining = total - index
    if remaining == 1:
        return "Finale"
    if remaining == 2:
        return "Demi-finales"
    if remaining == 3:
        return "Quarts de finale"
    return f"Tour {index + 1}"
