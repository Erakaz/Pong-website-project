#!/bin/sh
set -eu

echo "[backend] attente de PostgreSQL sur ${POSTGRES_HOST}:${POSTGRES_PORT}..."
python - <<'PYTHON'
import os
import socket
import sys
import time

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
deadline = time.monotonic() + 60

while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("[backend] PostgreSQL est joignable")
            sys.exit(0)
    except OSError:
        time.sleep(1)

print(f"[backend] PostgreSQL injoignable apres 60s sur {host}:{port}", file=sys.stderr)
sys.exit(1)
PYTHON

echo "[backend] application des migrations..."
python manage.py migrate --noinput

echo "[backend] demarrage de Daphne sur 0.0.0.0:8000"
exec daphne -b 0.0.0.0 -p 8000 --proxy-headers config.asgi:application
