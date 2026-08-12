"""Routes /api/ du jeu et des tournois."""

from django.urls import path

from game import views

urlpatterns = [
    path("games", views.matches, name="matches"),
    path("games/<uuid:match_id>", views.match_detail, name="match-detail"),
    path("games/<uuid:match_id>/state", views.match_state, name="match-state"),
    path("games/<uuid:match_id>/input", views.match_input, name="match-input"),
    path("games/<uuid:match_id>/join", views.match_join, name="match-join"),

    path("stats/dashboard", views.dashboard, name="dashboard"),
    path("stats/match/<uuid:match_id>", views.match_dashboard, name="match-dashboard"),

    path("tournaments", views.tournaments, name="tournaments"),
    path("tournaments/<uuid:tournament_id>", views.tournament_detail, name="tournament-detail"),
    path("tournaments/<uuid:tournament_id>/join", views.tournament_join, name="tournament-join"),
    path("tournaments/<uuid:tournament_id>/start", views.tournament_start,
         name="tournament-start"),
]
