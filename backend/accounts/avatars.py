"""Traitement des avatars televerses."""

from __future__ import annotations

import io

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from core.http import ApiError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

MAX_PIXELS = 40_000_000


def process(uploaded) -> ContentFile:
    """Valide et normalise un avatar. Retourne un fichier PNG pret a stocker."""
    if uploaded is None:
        raise ApiError("missing_file", "Aucun fichier recu.", 400, {"field": "avatar"})

    if uploaded.size > settings.AVATAR_MAX_BYTES:
        limit = settings.AVATAR_MAX_BYTES // 1024
        raise ApiError("file_too_large", f"L'avatar ne doit pas depasser {limit} Ko.", 413,
                       {"field": "avatar"})

    raw = uploaded.read()
    if not raw:
        raise ApiError("empty_file", "Le fichier est vide.", 400, {"field": "avatar"})

    try:
        probe = Image.open(io.BytesIO(raw))
        image_format = (probe.format or "").upper()
        width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError):
        raise ApiError("invalid_image", "Ce fichier n'est pas une image valide.", 400,
                       {"field": "avatar"}) from None

    if image_format not in ALLOWED_FORMATS:
        raise ApiError("unsupported_format",
                       "Formats acceptes : JPEG, PNG, WebP ou GIF.", 400,
                       {"field": "avatar"})

    if width * height > MAX_PIXELS:
        raise ApiError("image_too_large", "Image trop grande (trop de pixels).", 400,
                       {"field": "avatar"})

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGBA")
            image = _crop_to_square(image)
            side = min(settings.AVATAR_MAX_DIMENSION, image.width)
            image = image.resize((side, side), Image.LANCZOS)

            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
    except (OSError, ValueError):
        raise ApiError("invalid_image", "Cette image n'a pas pu etre traitee.", 400,
                       {"field": "avatar"}) from None

    return ContentFile(buffer.getvalue(), name="avatar.png")


def _crop_to_square(image: Image.Image) -> Image.Image:
    """Recadre au centre : les avatars s'affichent dans un cercle."""
    width, height = image.size
    if width == height:
        return image
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))
