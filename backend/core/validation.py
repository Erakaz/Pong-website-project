"""Validation des entrees utilisateur, cote serveur.

Le sujet impose une validation serveur de tous les formulaires et de toutes les
entrees. Chaque champ passe donc par une de ces fonctions, qui leve une
`ApiError` decrivant precisement le champ fautif.

Deux precautions systematiques :

* normalisation Unicode NFKC, pour qu'un pseudo ne puisse pas se faire passer
  pour un autre via des caracteres visuellement identiques mais encodes
  differemment ;
* suppression des caracteres de controle et des marques de direction, qui
  permettent des affichages trompeurs (texte inverse par RLO, par exemple).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from core.http import ApiError

# Plages de codepoints jamais legitimes dans un champ de formulaire. Elles sont
# ecrites en valeurs numeriques plutot qu'en litteraux : ces caracteres sont
# invisibles, les laisser tels quels dans le source le rendrait illisible et
# fragile au moindre copier-coller.
_FORBIDDEN_RANGES = (
    (0x0000, 0x001F),  # controles C0
    (0x007F, 0x009F),  # DEL et controles C1
    (0x200B, 0x200F),  # espaces de largeur nulle, marques LTR/RTL
    (0x202A, 0x202E),  # surcharges de direction bidirectionnelle
    (0x2066, 0x2069),  # isolats de direction
    (0xFEFF, 0xFEFF),  # BOM / espace insecable de largeur nulle
)


def _is_forbidden(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _FORBIDDEN_RANGES)


# Un pseudo lisible : lettres, chiffres, tiret, souligne, point, espaces
# simples. Ni espace en tete ou en fin, ni ponctuation isolee aux extremites.
_DISPLAY_NAME_RE = re.compile(r"^[^\W_][\w.\- ]{1,22}[^\W_]$", re.UNICODE)

# Un alias de tournoi, plus permissif car plus court.
_ALIAS_RE = re.compile(r"^[\w.\- ]+$", re.UNICODE)

# La RFC 5322 dans son integralite est inapplicable en pratique ; cette forme
# couvre les adresses reelles et rejette les tentatives d'injection.
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}$")

DISPLAY_NAME_MIN = 3
DISPLAY_NAME_MAX = 24
ALIAS_MIN = 1
ALIAS_MAX = 16
EMAIL_MAX = 254
PASSWORD_MAX = 128  # Borne haute : evite un deni de service par hachage Argon2.


def clean_text(value: str) -> str:
    """Normalise en NFKC et retire les caracteres invisibles ou de controle."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in normalized if not _is_forbidden(ch)).strip()


def _collapse_spaces(value: str) -> str:
    """« a  b » et « a b » doivent etre le meme nom pour le test d'unicite."""
    return re.sub(r"\s+", " ", value)


def field_str(
    data: dict[str, Any],
    name: str,
    *,
    required: bool = True,
    min_len: int = 0,
    max_len: int = 255,
    default: str = "",
    clean: bool = True,
) -> str:
    raw = data.get(name, None)
    if raw is None:
        if required:
            raise ApiError("missing_field", f"Le champ « {name} » est obligatoire.", 400,
                           {"field": name})
        return default
    if not isinstance(raw, str):
        raise ApiError("invalid_field", f"Le champ « {name} » doit etre une chaine.", 400,
                       {"field": name})

    value = clean_text(raw) if clean else raw
    if not value and not required:
        return default
    if len(value) < min_len:
        raise ApiError("invalid_field",
                       f"Le champ « {name} » doit faire au moins {min_len} caracteres.", 400,
                       {"field": name})
    if len(value) > max_len:
        raise ApiError("invalid_field",
                       f"Le champ « {name} » ne peut pas depasser {max_len} caracteres.", 400,
                       {"field": name})
    return value


def field_int(
    data: dict[str, Any],
    name: str,
    *,
    required: bool = True,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int = 0,
) -> int:
    raw = data.get(name, None)
    if raw is None:
        if required:
            raise ApiError("missing_field", f"Le champ « {name} » est obligatoire.", 400,
                           {"field": name})
        return default
    # `bool` derive de `int` : sans ce test, True passerait pour 1.
    if isinstance(raw, bool) or not isinstance(raw, int):
        try:
            raw = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ApiError("invalid_field", f"Le champ « {name} » doit etre un entier.", 400,
                           {"field": name}) from None
    if minimum is not None and raw < minimum:
        raise ApiError("invalid_field", f"Le champ « {name} » doit valoir au moins {minimum}.",
                       400, {"field": name})
    if maximum is not None and raw > maximum:
        raise ApiError("invalid_field", f"Le champ « {name} » doit valoir au plus {maximum}.",
                       400, {"field": name})
    return raw


def field_bool(data: dict[str, Any], name: str, *, default: bool = False) -> bool:
    raw = data.get(name, None)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    raise ApiError("invalid_field", f"Le champ « {name} » doit etre un booleen.", 400,
                   {"field": name})


def field_choice(
    data: dict[str, Any],
    name: str,
    choices: Iterable[str],
    *,
    required: bool = True,
    default: str = "",
) -> str:
    allowed = set(choices)
    value = field_str(data, name, required=required, max_len=64, default=default)
    if not value and not required:
        return default
    if value not in allowed:
        raise ApiError("invalid_field",
                       f"Le champ « {name} » doit valoir l'un de : {', '.join(sorted(allowed))}.",
                       400, {"field": name})
    return value


def validate_email(raw: str) -> str:
    """Verifie la forme de l'adresse et la normalise en minuscules."""
    value = clean_text(raw).lower()
    if len(value) > EMAIL_MAX or not _EMAIL_RE.match(value):
        raise ApiError("invalid_email", "Adresse e-mail invalide.", 400, {"field": "email"})
    return value


def validate_display_name(raw: str) -> str:
    """Pseudo affiche publiquement et utilise comme alias de tournoi."""
    value = _collapse_spaces(clean_text(raw))
    if not (DISPLAY_NAME_MIN <= len(value) <= DISPLAY_NAME_MAX) \
            or not _DISPLAY_NAME_RE.match(value):
        raise ApiError(
            "invalid_display_name",
            f"Le pseudo doit faire {DISPLAY_NAME_MIN} a {DISPLAY_NAME_MAX} caracteres et ne "
            f"contenir que des lettres, chiffres, espaces, tirets, points ou soulignes.",
            400,
            {"field": "display_name"},
        )
    return value


def validate_alias(raw: str) -> str:
    """Alias saisi a l'inscription d'un tournoi local (joueur non inscrit)."""
    value = _collapse_spaces(clean_text(raw))
    if not (ALIAS_MIN <= len(value) <= ALIAS_MAX) or not _ALIAS_RE.match(value):
        raise ApiError(
            "invalid_alias",
            f"Un alias doit faire {ALIAS_MIN} a {ALIAS_MAX} caracteres et ne contenir que des "
            f"lettres, chiffres, espaces, tirets, points ou soulignes.",
            400,
            {"field": "alias"},
        )
    return value


def validate_password(raw: str, user: Any = None) -> str:
    """Delegue aux validateurs Django configures (longueur, trivialite, ...).

    Argon2 accepte n'importe quelle longueur ; borner a 128 caracteres evite
    qu'un corps de 64 Kio ne monopolise un worker pendant le hachage.
    """
    if not isinstance(raw, str) or not raw:
        raise ApiError("missing_field", "Le mot de passe est obligatoire.", 400,
                       {"field": "password"})
    if len(raw) > PASSWORD_MAX:
        raise ApiError("invalid_password",
                       f"Le mot de passe ne peut pas depasser {PASSWORD_MAX} caracteres.", 400,
                       {"field": "password"})
    try:
        django_validate_password(raw, user)
    except DjangoValidationError as exc:
        raise ApiError("weak_password", " ".join(exc.messages), 400,
                       {"field": "password"}) from None
    return raw
