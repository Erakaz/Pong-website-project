"""Routes des comptes, montees sous /api/."""

from django.urls import path

from accounts import views, views_auth2, views_gdpr

urlpatterns = [
    # --- RGPD (module GDPR Compliance Options) ---
    path("privacy", views_gdpr.privacy_summary, name="privacy"),
    path("me/data", views_gdpr.export_data, name="export-data"),
    path("me/anonymize", views_gdpr.anonymize, name="anonymize"),
    path("me/delete", views_gdpr.delete_account, name="delete-account"),

    # --- Authentification ---
    path("auth/register", views.register, name="register"),
    path("auth/login", views.login, name="login"),
    path("auth/refresh", views.refresh, name="refresh"),
    path("auth/logout", views.logout, name="logout"),
    path("auth/logout-all", views.logout_all, name="logout-all"),

    # --- Double authentification (module 2FA + JWT) ---
    path("auth/2fa/verify", views_auth2.twofa_verify, name="twofa-verify"),
    path("me/2fa", views_auth2.twofa_status, name="twofa-status"),
    path("me/2fa/setup", views_auth2.twofa_setup, name="twofa-setup"),
    path("me/2fa/enable", views_auth2.twofa_enable, name="twofa-enable"),
    path("me/2fa/disable", views_auth2.twofa_disable, name="twofa-disable"),

    # --- Connexion 42 (module Remote authentication) ---
    path("auth/oauth42/login", views_auth2.oauth42_login, name="oauth42-login"),
    path("auth/oauth42/callback", views_auth2.oauth42_callback, name="oauth42-callback"),
    path("me/oauth42/link", views_auth2.oauth42_link_start, name="oauth42-link"),

    # --- Compte courant ---
    path("me", views.me, name="me"),
    path("me/password", views.change_password, name="change-password"),
    path("me/avatar", views.avatar, name="avatar"),
    path("me/matches", views.my_matches, name="my-matches"),

    # --- Autres joueurs ---
    path("users", views.users, name="users"),
    path("users/<int:user_id>", views.user_detail, name="user-detail"),

    # --- Amis ---
    path("friends", views.friends, name="friends"),
    path("friends/<int:friendship_id>/accept", views.friend_accept, name="friend-accept"),
    path("friends/<int:friendship_id>", views.friend_remove, name="friend-remove"),
]
