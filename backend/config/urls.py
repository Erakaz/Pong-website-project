"""Table de routage HTTP.

Tout l'applicatif est sous /api/ : nginx sert le frontend statique et ne
transmet a Django que ce prefixe (plus /ws/ pour les WebSockets).
"""

from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("api/health", core_views.health, name="health"),
    path("api/", include("accounts.urls")),
    path("api/", include("game.urls")),
    path("api/chat/", include("chat.urls")),
]

# Les erreurs doivent rester du JSON : la SPA parse toutes les reponses de
# l'API, une page HTML d'erreur Django provoquerait une exception en console.
handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
