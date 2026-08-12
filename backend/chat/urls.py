"""Routes /api/chat/."""

from django.urls import path

from chat import views

urlpatterns = [
    path("conversations", views.conversations, name="conversations"),
    path("with/<int:user_id>", views.conversation, name="conversation"),
    path("with/<int:user_id>/block", views.block, name="block"),
    path("with/<int:user_id>/invite", views.invite, name="invite"),
    path("invitations/<uuid:match_id>", views.invitation_match, name="invitation-match"),
]
