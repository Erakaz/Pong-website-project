#!/usr/bin/env python3
"""Remplace les valeurs `change-me...` d'un fichier .env par des secrets forts.

Usage:  python3 tools/gen_secrets.py [.env]

Les secrets sont tires de `secrets.token_urlsafe`, qui s'appuie sur le CSPRNG
du systeme d'exploitation. Le script est idempotent : il ne touche qu'aux
lignes dont la valeur commence par `change-me`, donc le relancer ne regenere
pas des secrets deja definis.
"""

import re
import secrets
import sys
from pathlib import Path

# Longueur (en octets d'entropie) de chaque secret genere.
ENTROPY_BYTES = {
    "DJANGO_SECRET_KEY": 48,
    "JWT_SECRET": 48,
    "POSTGRES_PASSWORD": 24,
}
DEFAULT_ENTROPY = 32

LINE_RE = re.compile(r"^(?P<key>[A-Z0-9_]+)=(?P<value>.*)$")


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else ".env")
    if not path.is_file():
        print(f"[gen_secrets] fichier introuvable : {path}", file=sys.stderr)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    changed = []

    for i, line in enumerate(lines):
        match = LINE_RE.match(line)
        if not match:
            continue
        # `split('#')` casserait un mot de passe contenant un '#'; on ne
        # commente jamais en fin de ligne de secret, donc un strip suffit.
        value = match["value"].strip()
        if not value.startswith("change-me"):
            continue
        key = match["key"]
        lines[i] = f"{key}={secrets.token_urlsafe(ENTROPY_BYTES.get(key, DEFAULT_ENTROPY))}"
        changed.append(key)

    if not changed:
        print("[gen_secrets] rien a faire : aucun 'change-me' restant.")
        return 0

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[gen_secrets] {len(changed)} secret(s) generes : {', '.join(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
