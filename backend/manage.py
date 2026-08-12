#!/usr/bin/env python
"""Utilitaire en ligne de commande de Django."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - diagnostic de demarrage
        raise ImportError(
            "Django est introuvable. L'environnement virtuel est-il actif ? "
            "Les dependances sont dans backend/requirements.txt."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
