"""Routes RGPD.

Les deux gestes irreversibles exigent de saisir a nouveau son mot de passe :
un onglet laisse ouvert ne doit pas suffire a effacer un compte.
"""

from __future__ import annotations

import json

from django.http import HttpResponse

from accounts import gdpr, tokens
from core.http import ApiError, json_ok, login_required, read_json, require_methods


def _confirm_identity(request) -> None:
    """Verifie le mot de passe, ou le pseudo pour un compte sans mot de passe."""
    data = read_json(request)
    user = request.user

    if user.has_usable_password():
        password = data.get("password")
        if not isinstance(password, str) or not user.check_password(password):
            raise ApiError("invalid_credentials", "Mot de passe incorrect.", 403,
                           {"field": "password"})
        return

    # Compte cree via 42 : pas de mot de passe a verifier. On demande de
    # recopier son pseudo, comme le font la plupart des services pour une
    # action destructrice.
    confirmation = data.get("confirm")
    if confirmation != user.display_name:
        raise ApiError("confirmation_mismatch",
                       "Recopie exactement ton pseudo pour confirmer.", 403,
                       {"field": "confirm"})


@require_methods("GET")
@login_required
def export_data(request):
    """Droit d'acces et de portabilite : tout, en un fichier JSON."""
    payload = gdpr.export(request.user)
    response = HttpResponse(
        json.dumps(payload, indent=2, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="mes-donnees-{request.user.pk}.json"')
    return response


@require_methods("POST")
@login_required
def anonymize(request):
    _confirm_identity(request)
    gdpr.anonymize(request.user)
    # Le compte devient inutilisable : on nettoie aussi les cookies de session.
    return tokens.clear_session(json_ok({"ok": True, "anonymized": True}))


@require_methods("POST")
@login_required
def delete_account(request):
    _confirm_identity(request)
    gdpr.delete_account(request.user)
    return tokens.clear_session(json_ok({"ok": True, "deleted": True}))


@require_methods("GET")
def privacy_summary(request):
    """Resume machine-lisible de ce que le site conserve et pourquoi.

    Le sujet demande « clear and transparent communication with users regarding
    their data privacy rights ». Le texte affiche vient d'ici, pour rester au
    meme endroit que le code qui met ces regles en oeuvre.
    """
    return json_ok({
        "collected": [
            {"name": "Adresse e-mail",
             "why": "Identifiant de connexion et recuperation de compte.",
             "retention": "Jusqu'a la suppression du compte."},
            {"name": "Pseudo et avatar",
             "why": "Vous identifier aupres des autres joueurs.",
             "retention": "Jusqu'a la suppression du compte."},
            {"name": "Historique des parties",
             "why": "Afficher vos statistiques et celles de vos adversaires.",
             "retention": "Conserve sous un nom neutre apres anonymisation."},
            {"name": "Messages",
             "why": "Faire fonctionner la messagerie directe.",
             "retention": "Contenu efface a l'anonymisation ou a la suppression."},
            {"name": "Secret de double authentification",
             "why": "Verifier les codes a usage unique, si vous l'activez.",
             "retention": "Efface des que la 2FA est desactivee."},
        ],
        "not_collected": [
            "Aucune adresse IP n'est conservee en base.",
            "Aucun traceur publicitaire, aucun service tiers d'analyse.",
            "Aucune donnee n'est transmise a un tiers.",
        ],
        "rights": [
            {"name": "Acces et portabilite",
             "how": "Telecharger l'integralite de vos donnees en JSON."},
            {"name": "Rectification", "how": "Modifier votre profil a tout moment."},
            {"name": "Anonymisation",
             "how": "Effacer toute donnee identifiante en conservant l'historique "
                    "des parties sous un nom neutre."},
            {"name": "Effacement",
             "how": "Supprimer definitivement le compte et tout ce qui s'y rattache."},
        ],
    })
