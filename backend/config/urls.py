"""Table de routage HTTP."""

from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("api/health", core_views.health, name="health"),
    path("api/", include("accounts.urls")),
    path("api/", include("game.urls")),
    path("api/chat/", include("chat.urls")),
]

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
